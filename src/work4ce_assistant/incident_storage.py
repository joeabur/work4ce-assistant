"""Bound multi-source incident coordination; no report mutation or response execution."""
from __future__ import annotations

import json
from contextlib import contextmanager
import re
from typing import Any
from uuid import UUID,uuid4

from sqlalchemy import and_,or_,select,update

from .contracts import Work4ceError,canonical,digest
from .storage import Store,case_coordination,incident_activity,incident_investigations,incidents_table,investigations,now

FIELDS=('id','investigation_id','creator','assignee','title','description','severity','status','revision',
        'created_by','created_at','updated_by','updated_at','resolution_note','resolved_by','resolved_at','closed_by','closed_at')
ACTIVITY_FIELDS=('id','incident_id','sequence','kind','actor','body','evidence_ids','from_status','to_status','created_at','references','linked_investigation_id')
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

    def _members(self,connection,tenant,identity):
        return [dict(row._mapping) for row in connection.execute(select(incident_investigations).where(
            incident_investigations.c.tenant==tenant,incident_investigations.c.incident_id==identity)
            .order_by(incident_investigations.c.investigation_id).limit(11))]

    def _lock_parents(self,connection,tenant,identities):
        # All writers acquire the complete parent set in the same global order.
        # Only after this loop may any coordination or incident row be locked.
        for identity in sorted(identities):
            if connection.dialect.name=='sqlite':
                connection.execute(update(investigations).where(investigations.c.tenant==tenant,
                    investigations.c.id==identity).values(updated_at=investigations.c.updated_at))
            parent=connection.execute(select(investigations.c.id).where(investigations.c.tenant==tenant,
                investigations.c.id==identity).with_for_update()).scalar_one_or_none()
            if parent is None:
                raise Work4ceError('incident_not_found',404)

    def _contexts(self,connection,tenant,primary,members,cases,*,lock=False):
        if not 1 <= len(members) <= 10 or primary not in {member['investigation_id'] for member in members}:
            raise Work4ceError('incident_integrity_failure',500)
        contexts={}
        for member in members:
            try:
                if (not isinstance(member['report_hash'],str) or re.fullmatch(r'[0-9a-f]{64}',member['report_hash']) is None
                        or not self.store._case_subject(member['linked_by']) or not self.store._case_timestamp(member['linked_at'])):
                    raise ValueError('invalid source metadata')
            except (ValueError,TypeError,KeyError):
                raise Work4ceError('incident_integrity_failure',500) from None
            identity=member['investigation_id']
            source,report=self._source(connection,tenant,identity,expected_hash=member['report_hash'],lock=lock)
            contexts[identity]={'case':cases[identity],'member':member,'report':report,'source':source}
        return contexts

    def _record(self,connection,tenant,subject,identity,*,all_cases=False,lock=False,prospective=None):
        if not isinstance(identity,str) or not 1 <= len(identity) <= 200:
            raise Work4ceError('invalid_incident_update',422)
        primary=connection.execute(select(incidents_table.c.investigation_id).where(
            incidents_table.c.tenant==tenant,incidents_table.c.id==identity)).scalar_one_or_none()
        if primary is None:
            raise Work4ceError('incident_not_found',404)
        before=self._members(connection,tenant,identity)
        source_ids={primary}|{member['investigation_id'] for member in before}
        if prospective is not None:
            source_ids.add(prospective)
        if any(not isinstance(value,str) or not 1 <= len(value) <= 200 for value in source_ids):
            raise Work4ceError('incident_integrity_failure',500)
        if lock:
            self._lock_parents(connection,tenant,source_ids)
        # Authenticate the complete source intersection before decoding any report
        # or private incident payload. Incident authorship never supplies a grant.
        cases={source:self._case(connection,tenant,subject,source,all_cases=all_cases,lock=lock)
               for source in sorted(source_ids)}
        statement=select(incidents_table).where(incidents_table.c.tenant==tenant,incidents_table.c.id==identity,
                                              incidents_table.c.investigation_id==primary)
        if lock:
            statement=statement.with_for_update()
        row=connection.execute(statement).first()
        if row is None:
            raise Work4ceError('incident_not_found',404)
        after=self._members(connection,tenant,identity)
        if before!=after:
            # A source linked while we waited is not in the acquired parent set.
            # Check visibility before reporting a conflict, then abort without a
            # write rather than extending the lock set out of sorted order.
            for member in after:
                self._case(connection,tenant,subject,member['investigation_id'],all_cases=all_cases)
            raise Work4ceError('incident_revision_conflict',409)
        contexts=self._contexts(connection,tenant,primary,after,cases,lock=lock)
        record=self._validate(row)
        anchor=contexts[primary]['member']
        if (record['report_hash']!=anchor['report_hash'] or record['created_by']!=anchor['linked_by']
                or record['created_at']!=anchor['linked_at']):
            raise Work4ceError('incident_integrity_failure',500)
        return record,cases[primary],contexts

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

    def _references(self,refs,contexts,*,allowed=None):
        if not isinstance(refs,(tuple,list)) or len(refs)>10:
            raise Work4ceError('invalid_incident_evidence',422)
        result=[]
        seen=set()
        for item in refs:
            if (not isinstance(item,dict) or set(item)!={'investigation_id','evidence_id'}
                    or not isinstance(item['investigation_id'],str) or not 1 <= len(item['investigation_id']) <= 200
                    or not isinstance(item['evidence_id'],str) or not 1 <= len(item['evidence_id']) <= 128):
                raise Work4ceError('invalid_incident_evidence',422)
            source,evidence=item['investigation_id'],item['evidence_id']
            key=(source,evidence)
            if key in seen or source not in contexts or allowed is not None and source not in allowed:
                raise Work4ceError('invalid_incident_evidence',422)
            self._evidence([evidence],contexts[source]['report'])
            seen.add(key)
            result.append({'investigation_id':source,'evidence_id':evidence})
        return result

    def _history(self,connection,record,contexts):
        rows=connection.execute(select(incident_activity).where(incident_activity.c.tenant==record['tenant'],
            incident_activity.c.incident_id==record['id']).order_by(incident_activity.c.sequence).limit(201)).all()
        if len(rows)!=record['revision']:
            raise Work4ceError('incident_integrity_failure',500)
        history=[]
        status=None
        resolution=(None,None,None)
        closure=(None,None)
        primary=record['investigation_id']
        linked={primary}
        try:
            for sequence,row in enumerate(rows,1):
                item=dict(row._mapping)
                if (item['sequence']!=sequence or str(UUID(item['id']))!=item['id']
                        or not self.store._case_subject(item['actor']) or not self.store._case_timestamp(item['created_at'])
                        or not isinstance(item['body'],str) or len(item['body'])>2000
                        or not isinstance(item['evidence_ids'],str) or len(item['evidence_ids'])>8192
                        or not isinstance(item['references'],str) or len(item['references'])>24576):
                    raise ValueError('invalid activity')
                ids=self._evidence(json.loads(item['evidence_ids']),contexts[primary]['report'])
                stored_refs=json.loads(item['references'])
                if stored_refs:
                    refs=self._references(stored_refs,contexts,allowed=linked)
                    # Structured notes also retain the primary-only subset for
                    # v6 clients. This is not the request-level mixed-form rule.
                    if ids!=[ref['evidence_id'] for ref in refs if ref['investigation_id']==primary]:
                        raise ValueError('primary reference subset mismatch')
                else:
                    if stored_refs!=[]:
                        raise ValueError('invalid reference representation')
                    refs=[{'investigation_id':primary,'evidence_id':value} for value in ids]
                item['evidence_ids']=ids
                item['references']=refs
                target=item['linked_investigation_id']
                if item['kind']=='created':
                    if (sequence!=1 or item['from_status'] is not None or item['to_status']!='open'
                            or item['body']!=record['description'] or item['actor']!=record['created_by']
                            or item['created_at']!=record['created_at'] or refs or target is not None):
                        raise ValueError('invalid creation')
                    status='open'
                elif item['kind']=='note':
                    if (sequence==1 or not item['body'].strip() or item['body']!=item['body'].strip()
                            or item['from_status'] is not None or item['to_status'] is not None or status=='closed' or target is not None):
                        raise ValueError('invalid note')
                elif item['kind']=='linked':
                    if (sequence==1 or status not in {'open','in_progress'} or not item['body'].strip()
                            or item['body']!=item['body'].strip() or refs or item['from_status'] is not None
                            or item['to_status'] is not None or not isinstance(target,str) or target in linked or target not in contexts):
                        raise ValueError('invalid source link')
                    membership=contexts[target]['member']
                    if membership['linked_by']!=item['actor'] or membership['linked_at']!=item['created_at']:
                        raise ValueError('source link metadata mismatch')
                    linked.add(target)
                elif item['kind']=='status':
                    legal={('open','in_progress'),('open','resolved'),('in_progress','resolved'),('resolved','closed'),('resolved','open'),('closed','open')}
                    if (sequence==1 or item['from_status']!=status or (status,item['to_status']) not in legal
                            or refs or target is not None or item['body']!=item['body'].strip()
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
            if (linked!=set(contexts) or status!=record['status'] or history[-1]['actor']!=record['updated_by']
                    or history[-1]['created_at']!=record['updated_at']
                    or resolution!=(record['resolution_note'],record['resolved_by'],record['resolved_at'])
                    or closure!=(record['closed_by'],record['closed_at'])):
                raise ValueError('activity state mismatch')
        except (ValueError,TypeError,KeyError,AttributeError,Work4ceError):
            raise Work4ceError('incident_integrity_failure',500) from None
        return history

    def _append(self,connection,record,subject,kind,body,*,evidence_ids=(),references=(),linked_investigation_id=None,
                from_status=None,to_status=None):
        connection.execute(incident_activity.insert().values(id=str(uuid4()),tenant=record['tenant'],incident_id=record['id'],
            sequence=record['revision'],kind=kind,actor=subject,body=body,evidence_ids=canonical(list(evidence_ids)),
            from_status=from_status,to_status=to_status,created_at=record['updated_at'],
            references=canonical(list(references)),linked_investigation_id=linked_investigation_id))
        self.store._audit(connection,record['tenant'],subject,'incident.'+{'created':'create','status':'status','note':'note','linked':'link'}[kind],
                          record['id'],'revision:'+str(record['revision']))

    def create(self,tenant,subject,investigation_id,title,description,severity,*,manage=False):
        self._flags(tenant,subject,manage)
        title=self._text(title,200,required=True)
        if not isinstance(description,str) or len(description)>2000 or not isinstance(severity,str) or severity not in {'low','medium','high','critical'}:
            raise Work4ceError('invalid_incident_update',422)
        with self.store._connection(write=True) as connection:
            case=self._case(connection,tenant,subject,investigation_id,all_cases=manage,lock=True)
            bound=connection.execute(select(incident_investigations.c.incident_id).where(
                incident_investigations.c.tenant==tenant,incident_investigations.c.investigation_id==investigation_id)).first()
            if bound is not None:
                # A source does not disclose an existing group's existence to an
                # actor lacking access to any of its other members. Do not add
                # locks to the already acquired single-source set out of order;
                # this is a read-only conflict path with no durable mutation.
                primary=connection.execute(select(incidents_table.c.investigation_id).where(
                    incidents_table.c.tenant==tenant,incidents_table.c.id==bound.incident_id)).scalar_one_or_none()
                if primary is None:
                    raise Work4ceError('incident_not_found',404)
                members=self._members(connection,tenant,bound.incident_id)
                for source_id in sorted({primary}|{item['investigation_id'] for item in members}):
                    self._case(connection,tenant,subject,source_id,all_cases=manage)
                if not 1 <= len(members) <= 10 or primary not in {item['investigation_id'] for item in members}:
                    raise Work4ceError('incident_integrity_failure',500)
                raise Work4ceError('incident_exists',409)
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
            membership=connection.execute(insert(incident_investigations).values(tenant=tenant,investigation_id=investigation_id,
                incident_id=record['id'],report_hash=source.report_hash,linked_by=subject,linked_at=instant)
                .on_conflict_do_nothing(index_elements=['tenant','investigation_id']).returning(incident_investigations.c.incident_id)).scalar_one_or_none()
            if membership is None:
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
            identity=connection.execute(select(incident_investigations.c.incident_id).where(incident_investigations.c.tenant==tenant,
                incident_investigations.c.investigation_id==investigation_id)).scalar_one_or_none()
            if identity is None:
                raise Work4ceError('incident_not_found',404)
            record,case,report=self._record(connection,tenant,subject,identity,all_cases=all_cases)
            self._history(connection,record,report)
            return self._view(record,case)

    def list(self,tenant,subject,*,all_cases=False,limit=50):
        self._flags(tenant,subject,all_cases)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise Work4ceError('invalid_incident_update',422)
        parent=investigations.alias('primary_source')
        primary_case=case_coordination.alias('primary_case')
        joined=incidents_table.join(parent,and_(incidents_table.c.investigation_id==parent.c.id,
            incidents_table.c.tenant==parent.c.tenant)).outerjoin(primary_case,and_(
                primary_case.c.investigation_id==parent.c.id,primary_case.c.tenant==parent.c.tenant))
        statement=select(incidents_table.c.id).select_from(joined).where(incidents_table.c.tenant==tenant)
        if not all_cases:
            member=incident_investigations.alias('scoped_member')
            source=investigations.alias('scoped_source')
            assigned=case_coordination.alias('scoped_case')
            scope_join=member.outerjoin(source,and_(member.c.investigation_id==source.c.id,member.c.tenant==source.c.tenant))
            scope_join=scope_join.outerjoin(assigned,and_(assigned.c.investigation_id==source.c.id,assigned.c.tenant==source.c.tenant))
            invisible=select(member.c.investigation_id).select_from(scope_join).where(
                member.c.tenant==tenant,member.c.incident_id==incidents_table.c.id,
                or_(source.c.id.is_(None),and_(source.c.subject!=subject,
                    or_(assigned.c.assignee.is_(None),assigned.c.assignee!=subject)))).exists()
            statement=statement.where(or_(parent.c.subject==subject,primary_case.c.assignee==subject),~invisible)
        statement=statement.order_by(incidents_table.c.updated_at.desc(),incidents_table.c.id.desc()).limit(limit)
        # One consistent read view avoids false integrity failures when source
        # membership or assignment changes between selecting IDs and projection.
        with self._snapshot() as connection:
            identities=connection.execute(statement).scalars().all()
            result=[]
            for identity in identities:
                record,case,_=self._record(connection,tenant,subject,identity,all_cases=all_cases)
                result.append(self._view(record,case))
            return result

    def activity(self,tenant,subject,incident_id,*,all_cases=False):
        self._flags(tenant,subject,all_cases)
        with self._snapshot() as connection:
            record,_,report=self._record(connection,tenant,subject,incident_id,all_cases=all_cases)
            return self._history(connection,record,report)

    def _writable(self,connection,tenant,subject,identity,expected_revision,manage,*,prospective=None):
        record,case,report=self._record(connection,tenant,subject,identity,all_cases=manage,lock=True,prospective=prospective)
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
            record,case,contexts=self._writable(connection,tenant,subject,incident_id,expected_revision,manage)
            old=record['status']
            legal={('open','in_progress'),('open','resolved'),('in_progress','resolved'),('resolved','closed'),('resolved','open'),('closed','open')}
            if (old,status) not in legal:
                raise Work4ceError('incident_transition_invalid',409)
            if (old,status)!=('open','in_progress') and not comment:
                raise Work4ceError('invalid_incident_update',422)
            if (status=='closed' or old=='closed') and not manage:
                raise Work4ceError('incident_management_required',403)
            if status in {'resolved','closed'} and any(item['case']['escalation_state']=='requested' for item in contexts.values()):
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

    def add_note(self,tenant,subject,incident_id,expected_revision,body,evidence_ids=(),*,references=(),manage=False):
        self._flags(tenant,subject,manage)
        self._revision(expected_revision)
        body=self._text(body,2000,required=True)
        if evidence_ids and references:
            raise Work4ceError('invalid_incident_evidence',422)
        with self.store._connection(write=True) as connection:
            record,case,contexts=self._writable(connection,tenant,subject,incident_id,expected_revision,manage)
            if record['status']=='closed':
                raise Work4ceError('incident_closed',409)
            primary=record['investigation_id']
            if references:
                # Validate the legacy empty argument too, so malformed false-y
                # values cannot slip through when using the structured form.
                self._evidence(evidence_ids,contexts[primary]['report'])
                refs=self._references(references,contexts)
                ids=[ref['evidence_id'] for ref in refs if ref['investigation_id']==primary]
            else:
                if not isinstance(references,(tuple,list)):
                    raise Work4ceError('invalid_incident_evidence',422)
                ids=self._evidence(evidence_ids,contexts[primary]['report'])
                refs=[{'investigation_id':primary,'evidence_id':value} for value in ids]
            updated=self._write(connection,record,dict(revision=expected_revision+1,updated_by=subject,updated_at=now()))
            self._append(connection,updated,subject,'note',body,evidence_ids=ids,references=refs)
            return self._view(updated,case)

    def link_investigation(self,tenant,subject,incident_id,expected_revision,investigation_id,comment,*,manage=False):
        self._flags(tenant,subject,manage)
        self._revision(expected_revision)
        comment=self._text(comment,2000,required=True)
        if not isinstance(investigation_id,str) or not 1 <= len(investigation_id) <= 200:
            raise Work4ceError('invalid_incident_update',422)
        with self.store._connection(write=True) as connection:
            record,case,contexts=self._writable(connection,tenant,subject,incident_id,expected_revision,manage,
                                                prospective=investigation_id)
            if record['status'] not in {'open','in_progress'}:
                raise Work4ceError('incident_not_active',409)
            bound=connection.execute(select(incident_investigations.c.incident_id).where(
                incident_investigations.c.tenant==tenant,incident_investigations.c.investigation_id==investigation_id)).first()
            if bound is not None:
                raise Work4ceError('incident_source_conflict',409)
            if len(contexts)>=10:
                raise Work4ceError('incident_source_limit',409)
            source,_=self._source(connection,tenant,investigation_id,lock=True)
            instant=now()
            updated=self._write(connection,record,dict(revision=expected_revision+1,updated_by=subject,updated_at=instant))
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert
            insert=sqlite_insert if connection.dialect.name=='sqlite' else pg_insert
            linked=connection.execute(insert(incident_investigations).values(tenant=tenant,investigation_id=investigation_id,
                incident_id=incident_id,report_hash=source.report_hash,linked_by=subject,linked_at=instant)
                .on_conflict_do_nothing(index_elements=['tenant','investigation_id']).returning(incident_investigations.c.incident_id)).scalar_one_or_none()
            if linked is None:
                raise Work4ceError('incident_source_conflict',409)
            self._append(connection,updated,subject,'linked',comment,linked_investigation_id=investigation_id)
            return self._view(updated,case)

    def sources(self,tenant,subject,incident_id,*,all_cases=False):
        self._flags(tenant,subject,all_cases)
        with self._snapshot() as connection:
            record,_,contexts=self._record(connection,tenant,subject,incident_id,all_cases=all_cases)
            self._history(connection,record,contexts)
            primary=record['investigation_id']
            result=[]
            for identity,item in sorted(contexts.items(),key=lambda pair:(pair[0]!=primary,pair[1]['member']['linked_at'],pair[0])):
                report=item['report']
                query=report.get('query')
                if not isinstance(query,str) or len(query)>200:
                    query=None
                choices=[]
                seen=set()
                evidence=report.get('evidence',[])
                if isinstance(evidence,list):
                    for entry in evidence:
                        if not isinstance(entry,dict):
                            continue
                        evidence_id=entry.get('evidence_id')
                        content=entry.get('content')
                        summary=content.get('summary') if isinstance(content,dict) else None
                        if (isinstance(evidence_id,str) and 1 <= len(evidence_id) <= 128 and evidence_id not in seen
                                and isinstance(summary,str) and len(summary)<=2000):
                            choices.append({'evidence_id':evidence_id,'summary':summary})
                            seen.add(evidence_id)
                            if len(choices)>=100:
                                break
                result.append({'investigation_id':identity,'primary':identity==primary,'creator':item['case']['creator'],
                    'assignee':item['case']['assignee'],'escalation_state':item['case']['escalation_state'],'query':query,
                    'linked_by':item['member']['linked_by'],'linked_at':item['member']['linked_at'],'evidence':choices})
            return result
