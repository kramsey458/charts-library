from __future__ import annotations


def test_pipeline_login_flow_requires_auth_in_bound_context(client):
    start_response = client.post('/api/pipeline/start')
    assert start_response.status_code == 201
    start_payload = start_response.get_json()

    assert start_payload['job_id']
    assert start_payload['playwright_context_id']
    assert '/api/pipeline/login/' in start_payload['login_url']

    session_id = start_payload['login_session_id']
    token = start_payload['login_url'].split('token=', 1)[1]

    open_response = client.get(f'/api/pipeline/login/{session_id}?token={token}')
    assert open_response.status_code == 200
    open_payload = open_response.get_json()
    assert open_payload['status'] == 'login_in_progress'

    repeat_open_response = client.get(f'/api/pipeline/login/{session_id}?token={token}')
    assert repeat_open_response.status_code == 410

    resume_response = client.post(f"/api/pipeline/resume-after-login/{start_payload['job_id']}")
    assert resume_response.status_code == 409
    resume_payload = resume_response.get_json()
    assert resume_payload['status'] == 'login_in_progress'
    assert 'authentication not detected' in resume_payload['error'].lower()


def test_pipeline_login_rejects_invalid_token(client):
    start_response = client.post('/api/pipeline/start')
    session_id = start_response.get_json()['login_session_id']

    open_response = client.get(f'/api/pipeline/login/{session_id}?token=wrong-token')
    assert open_response.status_code == 403
