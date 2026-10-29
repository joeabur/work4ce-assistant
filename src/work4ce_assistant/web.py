"""Same-origin static workbench with strict script policy and no persisted secrets."""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import re
from functools import lru_cache

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles

ASSETS = Path(__file__).parent / 'web_assets'


class PrivateResponses:
    """Authorization/data responses must never survive a browser session in cache."""
    def __init__(self, app):
        self.app=app

    async def __call__(self, scope, receive, send):
        if scope['type']!='http':
            return await self.app(scope,receive,send)
        async def secured(message):
            if message['type']=='http.response.start':
                headers=[(key,value) for key,value in message.get('headers',[])
                         if key.lower() not in {b'cache-control',b'pragma',b'x-content-type-options',
                                                b'referrer-policy',b'x-frame-options'}]
                headers.extend([(b'cache-control',b'no-store'),(b'pragma',b'no-cache'),
                                (b'x-content-type-options',b'nosniff'),(b'referrer-policy',b'no-referrer'),
                                (b'x-frame-options',b'DENY')])
                message={**message,'headers':headers}
            await send(message)
        await self.app(scope,receive,secured)


@lru_cache(maxsize=8)
def _html_policy(path: str, modified_ns: int) -> str:
    del modified_ns  # Part of the cache key; hash only trusted compiled inline scripts.
    contents=Path(path).read_bytes()
    scripts=re.findall(rb'<script\b[^>]*>(.*?)</script\s*>',contents,flags=re.DOTALL|re.IGNORECASE)
    hashes=["'sha256-"+base64.b64encode(hashlib.sha256(script).digest()).decode()+"'" for script in scripts if script]
    return ("default-src 'self'; script-src 'self' "+' '.join(hashes)+
            "; style-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


class WorkbenchFiles(StaticFiles):
    async def get_response(self,path,scope):
        response=await super().get_response(path,scope)
        filename=getattr(response,'path',None)
        if filename and str(filename).endswith('.html'):
            file=Path(filename)
            response.headers['Content-Security-Policy']=_html_policy(str(file),file.stat().st_mtime_ns)
        return response


def mount_workbench(app: FastAPI, assets: Path | None=None) -> None:
    assets=assets or ASSETS
    if (assets/'index.html').is_file():
        app.mount('/workbench',WorkbenchFiles(directory=str(assets),html=True),name='workbench')
    else:
        @app.get('/workbench',include_in_schema=False)
        @app.get('/workbench/',include_in_schema=False)
        async def unavailable():
            return JSONResponse({'error':'workbench_not_built'},status_code=503)
