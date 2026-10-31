import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import uuid

import httpx
import pytest
import websockets
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models import Base
from app.models.user import User, UserRole
from app.utils.security import hash_password


@pytest.mark.asyncio
async def test_real_server_commits_before_two_user_notifications(tmp_path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'runtime.sqlite3').as_posix()}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        session.add_all([User(id=uuid.uuid4(), username=name, full_name=name, role=role, hashed_password=hash_password('test-only-password')) for name, role in [('runtime_admin', UserRole.ADMIN), ('runtime_member', UserRole.MEMBER)]])
        await session.commit()
    await engine.dispose()
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    env = dict(os.environ, DATABASE_URL=url, SEED_DEMO_USERS='false')
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)], cwd=Path(__file__).resolve().parents[1], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}', timeout=5) as client:
            for _ in range(100):
                if process.poll() is not None:
                    raise AssertionError(process.stderr.read().decode(errors='replace'))
                try:
                    if (await client.get('/health')).status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(.1)
            else:
                raise AssertionError('Isolated server did not start')
            tokens = []
            for name in ('runtime_admin', 'runtime_member'):
                response = await client.post('/api/v1/auth/login', json={'username': name, 'password': 'test-only-password'})
                assert response.status_code == 200
                tokens.append(response.json())
            admin = {'Authorization': f"Bearer {tokens[0]['access_token']}"}
            member = {'Authorization': f"Bearer {tokens[1]['access_token']}"}
            pid = (await client.post('/api/v1/projects', json={'name': 'Runtime only'}, headers=admin)).json()['id']
            parent = (await client.post(f'/api/v1/projects/{pid}/tasks', json={'title': 'Parent'}, headers=admin)).json()['id']
            child = (await client.post(f'/api/v1/projects/{pid}/tasks', json={'title': 'Child', 'parent_task_id': parent}, headers=admin)).json()['id']
            ws_url = f'ws://127.0.0.1:{port}/ws'
            async with websockets.connect(ws_url, origin='http://localhost:5173') as first, websockets.connect(ws_url, origin='http://localhost:5173') as second:
                for ws, token in zip((first, second), tokens):
                    await ws.send(json.dumps({'token': token['access_token']}))
                    assert json.loads(await asyncio.wait_for(ws.recv(), 5))['type'] == 'connection.ready'
                assert (await client.post(f'/api/v1/tasks/{child}/progress', json={'progress_pct': 45, 'note': 'Runtime validation'}, headers=member)).status_code == 201
                for ws in (first, second):
                    event = json.loads(await asyncio.wait_for(ws.recv(), 5))
                    assert event == {'type': 'project.changed', 'data': {'project_id': pid}}
                    assert (await client.get(f'/api/v1/tasks/{parent}', headers=admin)).json()['progress_pct'] == 45
            async with websockets.connect(ws_url, origin='http://localhost:5173') as ws:
                await ws.send(json.dumps({'token': tokens[0]['refresh_token']}))
                with pytest.raises(websockets.exceptions.ConnectionClosed):
                    await ws.recv()
                assert ws.close_code == 4001
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if process.stderr:
            process.stderr.close()
