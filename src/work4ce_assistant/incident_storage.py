"""Single-source incident coordination; no report mutation or response execution."""
from __future__ import annotations

import json
from contextlib import contextmanager
import re
from typing import Any
from uuid import UUID,uuid4

from sqlalchemy import and_,or_,select,update

from .contracts import Work4ceError,canonical,digest
from .storage import Store,case_coordination,incident_activity,incidents_table,investigations,now

FIELDS=('id','investigation_id','creator','assignee','title','description','severity','status','revision',
        'created_by','created_at','updated_by','updated_at','resolution_note','resolved_by','resolved_at','closed_by','closed_at')
ACTIVITY_FIELDS=('id','incident_id','sequence','kind','actor','body','evidence_ids','from_status','to_status','created_at')
STATUSES=frozenset({'open','in_progress','resolved','closed'})


class IncidentRepository:
    def __init__(self,store: Store):
        self.store=store

    @contextmanager
    def _snapshot(self):
        """Keep authorization, incident revision and activity on one read view."""
        with self.store._connection() as connection:
            if connection.dialect.name=='sqlite':
                # sqlite3 legacy mode does not BEGIN for SELECT. An explicit
                # read transaction supplies a WAL snapshot without writing.
                connection.exec_driver_sql('BEGIN')
            else:
                connection=connection.execution_options(isolation_level='REPEATABLE READ')
            yield connection

    def _flags(self,tenant,subject,flag) -> None:
        if (not isinstance(tenant,str) or not 1 <= len(tenant) <= 200 or not self.store._case_subject(subject)
                or type(flag) is not bool):
            raise Work4ceError('invalid_incident_update',422)

    @staticmethod
    def _text(value,maximum,*,required=False) -> str:
        if not isinstance(value,str) or len(value)>maximum or required and not value.strip():
            raise Work4ceError('invalid_incident_update',422)
        return value.strip()

    @staticmethod
    def _revision(value) -> None:
        if type(value) is not int or not 1 <= value <= 200:
            raise Work4ceError('invalid_incident_update',422)

    def _case(self,connection,tenant,subject,identity,*,all_cases=False,lock=False):
        if not isinstance(identity,str) or not 1 <= len(identity) <= 200:
            raise Work4ceError('invalid_incident_update',422)
        try:
            return self.store._case(connection,tenant,subject,identity,all_cases=all_cases,lock=lock)[0]
        except Work4ceError as error:
            if error.status==404:
                raise Work4ceError('incident_not_found',404) from None
            raise

    def _source(self,connection,tenant,identity,*,expected_hash=None,lock=False):
        code='incident_report_mismatch' if expected_hash is not None else 'incident_source_incomplete'
        try:
            row,report=self.store._load_report(connection,tenant,identity,lock=lock)
            if (row.status!='completed' or not isinstance(report,dict) or report.get('synthetic') is not True
                    or expected_hash is not None and row.report_hash!=expected_hash):
                raise Work4ceError(code,409)
        except Work4ceError:
            raise Work4ceError(code,409) from None
        return row,report

    def _validate(self,row) -> dict:
        data=dict(row._mapping) if hasattr(row,'_mapping') else dict(row)
        try:
            if (str(UUID(data['id']))!=data['id'] or not isinstance(data['investigation_id'],str)
                    or type(data['revision']) is not int or not 1 <= data['revision'] <= 200
                    or data['status'] not in STATUSES or data['severity'] not in {'low','medium','high','critical'}
                    or not isinstance(data['report_hash'],str) or re.fullmatch(r'[0-9a-f]{64}',data['report_hash']) is None
                    or not isinstance(data['title'],str) or not 1 <= len(data['title']) <= 200 or data['title']!=data['title'].strip()
                    or not isinstance(data['description'],str) or len(data['description'])>2000
                    or not all(self.store._case_subject(data[k]) for k in ('created_by','updated_by'))
                    or not all(self.store._case_timestamp(data[k]) for k in ('created_at','updated_at'))):
                raise ValueError('invalid metadata')
            resolved=(data['resolution_note'],data['resolved_by'],data['resolved_at'])
            closed=(data['closed_by'],data['closed_at'])
            if data['status'] in {'open','in_progress'}:
                if any(value is not None for value in resolved+closed):
                    raise ValueError('unexpected resolution')
            else:
                if (not isinstance(resolved[0],str) or not 1 <= len(resolved[0]) <= 2000 or resolved[0]!=resolved[0].strip()
                        or not self.store._case_subject(resolved[1]) or not self.store._case_timestamp(resolved[2])):
                    raise ValueError('incomplete resolution')
                if data['status']=='resolved' and any(value is not None for value in closed):
                    raise ValueError('unexpected closure')
                if data['status']=='closed' and (not self.store._case_subject(closed[0]) or not self.store._case_timestamp(closed[1])):
                    raise ValueError('incomplete closure')
        except (ValueError,TypeError,KeyError,AttributeError):
            raise Work4ceError('incident_integrity_failure',500) from None
        return data

    @staticmethod
    def _view(record,case):
        data={**record,'creator':case['creator'],'assignee':case['assignee']}
        return {field:data[field] for field in FIELDS}

    def _record(self,connection,tenant,subject,identity,*,all_cases=False,lock=False):
        if not isinstance(identity,str) or not 1 <= len(identity) <= 200:
            raise Work4ceError('invalid_incident_update',422)
        source_id=connection.execute(select(incidents_table.c.investigation_id).where(
            incidents_table.c.tenant==tenant,incidents_table.c.id==identity)).scalar_one_or_none()
        if source_id is None:
            raise Work4ceError('incident_not_found',404)
        case=self._case(connection,tenant,subject,source_id,all_cases=all_cases,lock=lock)
        statement=select(incidents_table).where(incidents_table.c.tenant==tenant,incidents_table.c.id==identity,
                                              incidents_table.c.investigation_id==source_id)
        if lock:
            statement=statement.with_for_update()
        row=connection.execute(statement).first()
        if row is None:
            raise Work4ceError('incident_not_found',404)
        record=self._validate(row)
        _,report=self._source(connection,tenant,source_id,expected_hash=record['report_hash'],lock=lock)
        return record,case,report

    @staticmethod
    def _evidence(ids,report):
        if (not isinstance(ids,(tuple,list)) or len(ids)>10
                or any(not isinstance(value,str) or not 1 <= len(value) <= 128 for value in ids)
                or len(set(ids))!=len(ids)):
            raise Work4ceError('invalid_incident_evidence',422)
        evidence=report.get('evidence',[])
        known={item.get('evidence_id') for item in evidence if isinstance(item,dict) and isinstance(item.get('evidence_id'),str)} if isinstance(evidence,list) else set()
        if not set(ids)<=known:
            raise Work4ceError('invalid_incident_evidence',422)
        return list(ids)

    def _history(self,connection,record,report):
        rows=connection.execute(select(incident_activity).where(incident_activity.c.tenant==record['tenant'],
            incident_activity.c.incident_id==record['id']).order_by(incident_activity.c.sequence).limit(201)).all()
        if len(rows)!=record['revision']:
            raise Work4ceError('incident_integrity_failure',500)
        history=[]
        status=None
        resolution=(None,None,None)
        closure=(None,None)
        try:
            for sequence,row in enumerate(rows,1):
                item=dict(row._mapping)
                if (item['sequence']!=sequence or str(UUID(item['id']))!=item['id']
                        or not self.store._case_subject(item['actor']) or not self.store._case_timestamp(item['created_at'])
                        or not isinstance(item['body'],str) or len(item['body'])>2000
                        or not isinstance(item['evidence_ids'],str) or len(item['evidence_ids'])>8192):
                    raise ValueError('invalid activity')
                item['evidence_ids']=self._evidence(json.loads(item['evidence_ids']),report)
                if item['kind']=='created':
                    if (sequence!=1 or item['from_status'] is not None or item['to_status']!='open'
                            or item['body']!=record['description'] or item['actor']!=record['created_by']
                            or item['created_at']!=record['created_at'] or item['evidence_ids']):
                        raise ValueError('invalid creation')
                    status='open'
                elif item['kind']=='note':
                    if (sequence==1 or not item['body'].strip() or item['body']!=item['body'].strip()
                            or item['from_status'] is not None or item['to_status'] is not None or status=='closed'):
                        raise ValueError('invalid note')
                elif item['kind']=='status':
                    legal={('open','in_progress'),('open','resolved'),('in_progress','resolved'),('resolved','closed'),('resolved','open'),('closed','open')}
                    if (sequence==1 or item['from_status']!=status or (status,item['to_status']) not in legal
                            or item['evidence_ids'] or item['body']!=item['body'].strip()
                            or (status,item['to_status'])!=('open','in_progress') and not item['body']):
                        raise ValueError('invalid status transition')
                    status=item['to_status']
                    if status=='resolved':
                        resolution=(item['body'],item['actor'],item['created_at'])
                    elif status=='closed':
                        closure=(item['actor'],item['created_at'])
                    elif status=='open':
                        resolution=(None,None,None)
                        closure=(None,None)
                else:
                    raise ValueError('invalid activity kind')
                history.append({field:item[field] for field in ACTIVITY_FIELDS})
            if (status!=record['status'] or history[-1]['actor']!=record['updated_by']
                    or history[-1]['created_at']!=record['updated_at']
                    or resolution!=(record['resolution_note'],record['resolved_by'],record['resolved_at'])
                    or closure!=(record['closed_by'],record['closed_at'])):
                raise ValueError('activity state mismatch')
        except (ValueError,TypeError,KeyError,AttributeError,Work4ceError):
            raise Work4ceError('incident_integrity_failure',500) from None
        return history

    def _append(self,connection,record,subject,kind,body,*,evidence_ids=(),from_status=None,to_status=None):
        connection.execute(incident_activity.insert().values(id=str(uuid4()),tenant=record['tenant'],incident_id=record['id'],
            sequence=record['revision'],kind=kind,actor=subject,body=body,evidence_ids=canonical(list(evidence_ids)),
            from_status=from_status,to_status=to_status,created_at=record['updated_at']))
        self.store._audit(connection,record['tenant'],subject,'incident.'+{'created':'create','status':'status','note':'note'}[kind],
                          record['id'],'revision:'+str(record['revision']))

    def create(self,tenant,subject,investigation_id,title,description,severity,*,manage=False):
        self._flags(tenant,subject,manage)
        title=self._text(title,200,required=True)
        if not isinstance(description,str) or len(description)>2000 or not isinstance(severity,str) or severity not in {'low','medium','high','critical'}:
            raise Work4ceError('invalid_incident_update',422)
        with self.store._connection(write=True) as connection:
            case=self._case(connection,tenant,subject,investigation_id,all_cases=manage,lock=True)
            source,report=self._source(connection,tenant,investigation_id,lock=True)
            instant=now()
            record=dict(id=str(uuid4()),tenant=tenant,investigation_id=investigation_id,report_hash=source.report_hash,
                title=title,description=description,severity=severity,status='open',revision=1,created_by=subject,
                created_at=instant,updated_by=subject,updated_at=instant,resolution_note=None,resolved_by=None,
                resolved_at=None,closed_by=None,closed_at=None)
            self._validate(record)
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert
            insert=sqlite_insert if connection.dialect.name=='sqlite' else pg_insert
            created=connection.execute(insert(incidents_table).values(**record).on_conflict_do_nothing(
                index_elements=['tenant','investigation_id']).returning(incidents_table.c.id)).scalar_one_or_none()
            if created is None:
                raise Work4ceError('incident_exists',409)
            self._append(connection,record,subject,'created',description,to_status='open')
            return self._view(record,case)

    def get(self,tenant,subject,incident_id,*,all_cases=False):
        self._flags(tenant,subject,all_cases)
        with self._snapshot() as connection:
            record,case,report=self._record(connection,tenant,subject,incident_id,all_cases=all_cases)
            self._history(connection,record,report)
            return self._view(record,case)

    def for_investigation(self,tenant,subject,investigation_id,*,all_cases=False):
        self._flags(tenant,subject,all_cases)
        with self._snapshot() as connection:
            self._case(connection,tenant,subject,investigation_id,all_cases=all_cases)
            identity=connection.execute(select(incidents_table.c.id).where(incidents_table.c.tenant==tenant,
                incidents_table.c.investigation_id==investigation_id)).scalar_one_or_none()
            if identity is None:
                raise Work4ceError('incident_not_found',404)
            record,case,report=self._record(connection,tenant,subject,identity,all_cases=all_cases)
            self._history(connection,record,report)
            return self._view(record,case)

    def list(self,tenant,subject,*,all_cases=False,limit=50):
        self._flags(tenant,subject,all_cases)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise Work4ceError('invalid_incident_update',422)
        joined=incidents_table.join(investigations,and_(incidents_table.c.investigation_id==investigations.c.id,
            incidents_table.c.tenant==investigations.c.tenant)).outerjoin(case_coordination,and_(
                case_coordination.c.investigation_id==investigations.c.id,case_coordination.c.tenant==investigations.c.tenant))
        statement=select(incidents_table,investigations.c.subject.label('source_creator'),
            investigations.c.status.label('source_status'),investigations.c.report.label('source_report'),
            investigations.c.report_hash.label('source_report_hash'),
            *(column.label('case_'+column.name) for column in case_coordination.columns)).select_from(joined).where(incidents_table.c.tenant==tenant)
        if not all_cases:
            statement=statement.where(or_(investigations.c.subject==subject,case_coordination.c.assignee==subject))
        with self.store._connection() as connection:
            rows=connection.execute(statement.order_by(incidents_table.c.updated_at.desc(),incidents_table.c.id.desc()).limit(limit)).all()
        result=[]
        for row in rows:
            record=self._validate(row)
            case_data={column.name:row._mapping['case_'+column.name] for column in case_coordination.columns}
            case=self.store._case_data(row.source_creator,case_data if case_data['investigation_id'] is not None else None,identity=record['investigation_id'])
            try:
                source=json.loads(row.source_report)
                if (row.source_status!='completed' or not isinstance(source,dict) or source.get('synthetic') is not True
                        or digest(source)!=row.source_report_hash or record['report_hash']!=row.source_report_hash):
                    raise ValueError('report changed')
            except (ValueError,TypeError,RecursionError):
                raise Work4ceError('incident_report_mismatch',409) from None
            result.append(self._view(record,case))
        return result

    def activity(self,tenant,subject,incident_id,*,all_cases=False):
        self._flags(tenant,subject,all_cases)
        with self._snapshot() as connection:
            record,_,report=self._record(connection,tenant,subject,incident_id,all_cases=all_cases)
            return self._history(connection,record,report)

    def _writable(self,connection,tenant,subject,identity,expected_revision,manage):
        record,case,report=self._record(connection,tenant,subject,identity,all_cases=manage,lock=True)
        if record['revision']!=expected_revision:
            raise Work4ceError('incident_revision_conflict',409)
        if record['revision']>=200:
            raise Work4ceError('incident_history_limit',409)
        self._history(connection,record,report)
        return record,case,report

    def _write(self,connection,record,values):
        prospective=self._validate({**record,**values})
        changed=connection.execute(update(incidents_table).where(incidents_table.c.tenant==record['tenant'],
            incidents_table.c.id==record['id'],incidents_table.c.revision==record['revision']).values(**values))
        if changed.rowcount!=1:
            raise Work4ceError('incident_revision_conflict',409)
        return prospective

    def transition(self,tenant,subject,incident_id,expected_revision,status,comment='',*,manage=False):
        self._flags(tenant,subject,manage)
        self._revision(expected_revision)
        if not isinstance(status,str) or status not in STATUSES:
            raise Work4ceError('invalid_incident_update',422)
        comment=self._text(comment,2000)
        with self.store._connection(write=True) as connection:
            record,case,_=self._writable(connection,tenant,subject,incident_id,expected_revision,manage)
            old=record['status']
            legal={('open','in_progress'),('open','resolved'),('in_progress','resolved'),('resolved','closed'),('resolved','open'),('closed','open')}
            if (old,status) not in legal:
                raise Work4ceError('incident_transition_invalid',409)
            if (old,status)!=('open','in_progress') and not comment:
                raise Work4ceError('invalid_incident_update',422)
            if (status=='closed' or old=='closed') and not manage:
                raise Work4ceError('incident_management_required',403)
            if status in {'resolved','closed'} and case['escalation_state']=='requested':
                raise Work4ceError('incident_escalation_pending',409)
            instant=now()
            values=dict(status=status,revision=expected_revision+1,updated_by=subject,updated_at=instant)
            if status=='resolved':
                values.update(resolution_note=comment,resolved_by=subject,resolved_at=instant)
            elif status=='closed':
                values.update(closed_by=subject,closed_at=instant)
            elif status=='open':
                values.update(resolution_note=None,resolved_by=None,resolved_at=None,closed_by=None,closed_at=None)
            updated=self._write(connection,record,values)
            self._append(connection,updated,subject,'status',comment,from_status=old,to_status=status)
            return self._view(updated,case)

    def add_note(self,tenant,subject,incident_id,expected_revision,body,evidence_ids=(),*,manage=False):
        self._flags(tenant,subject,manage)
        self._revision(expected_revision)
        body=self._text(body,2000,required=True)
        with self.store._connection(write=True) as connection:
            record,case,report=self._writable(connection,tenant,subject,incident_id,expected_revision,manage)
            if record['status']=='closed':
                raise Work4ceError('incident_closed',409)
            ids=self._evidence(evidence_ids,report)
            updated=self._write(connection,record,dict(revision=expected_revision+1,updated_by=subject,updated_at=now()))
            self._append(connection,updated,subject,'note',body,evidence_ids=ids)
            return self._view(updated,case)
