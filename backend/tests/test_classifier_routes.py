from __future__ import annotations

import io

import cv2
import numpy as np


def _png_bytes_with_color(bgr: tuple[int, int, int]) -> bytes:
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2.rectangle(image, (20, 20), (260, 170), bgr, -1)
    ok, encoded = cv2.imencode('.png', image)
    assert ok
    return encoded.tobytes()


def test_classifier_config_and_preview_happy_path(client):
    config_response = client.get('/api/classifier/config')
    assert config_response.status_code == 200
    config_payload = config_response.get_json()['config']
    assert 'roi' in config_payload

    preview_response = client.post(
        '/api/classifier/preview',
        data={
            'include_overlay': 'true',
            'image': (io.BytesIO(_png_bytes_with_color((0, 0, 255))), 'red.png'),
        },
        content_type='multipart/form-data',
    )

    assert preview_response.status_code == 200
    payload = preview_response.get_json()
    assert payload['label'] == 'red'
    assert payload['red_pixels'] > payload['yellow_pixels']
    assert payload['decision_reason'] == 'red_dominant_by_ratio'
    assert payload['overlay_image_base64']


def test_classifier_put_config_rejects_invalid_hsv_and_roi(client):
    invalid_payload = {
        'roi': {'x': -1, 'y': 0, 'width': 300, 'height': 100},
        'red_range_1': {'lower': [0, 80, 80], 'upper': [10, 255, 255]},
        'red_range_2': {'lower': [170, 80, 80], 'upper': [180, 255, 255]},
        'yellow_range': {'lower': [181, 80, 80], 'upper': [40, 255, 255]},
        'min_pixels': 50,
        'dominance_ratio': 1.2,
    }

    response = client.put('/api/classifier/config', json=invalid_payload)

    assert response.status_code == 400
    assert 'error' in response.get_json()


def test_classifier_preview_rejects_malformed_png(client):
    response = client.post(
        '/api/classifier/preview',
        data={'image': (io.BytesIO(b'not-a-real-png'), 'broken.png')},
        content_type='multipart/form-data',
    )

    assert response.status_code == 400
    assert response.get_json()['error'] == 'Malformed PNG image.'


def test_classifier_batch_plan_and_upload(client):
    plan_response = client.post(
        '/api/classifier/batch/plan',
        data={
            'charts': [
                (io.BytesIO(_png_bytes_with_color((0, 255, 255))), 'aapl_20260212_signal.png'),
                (io.BytesIO(_png_bytes_with_color((0, 0, 255))), 'tsla_20260212_signal.png'),
            ]
        },
        content_type='multipart/form-data',
    )
    assert plan_response.status_code == 200
    plan_results = plan_response.get_json()['results']
    assert len(plan_results) == 2
    assert {item['decision'] for item in plan_results} == {'accept', 'reject'}
    assert all('ticker' in item and 'date' in item for item in plan_results)

    upload_response = client.post(
        '/api/classifier/batch/upload',
        data={
            'charts': [
                (io.BytesIO(_png_bytes_with_color((0, 255, 255))), 'msft_20260213_signal.png'),
            ]
        },
        content_type='multipart/form-data',
    )
    assert upload_response.status_code == 200
    upload_result = upload_response.get_json()['results'][0]
    assert upload_result['decision'] == 'accept'
    assert upload_result['upload_result']['status'] == 201

    charts = client.get('/api/charts/MSFT').get_json()['charts']
    assert len(charts) == 1


def test_classifier_batch_upload_reports_per_file_errors(client):
    response = client.post(
        '/api/classifier/batch/upload',
        data={
            'charts': [
                (io.BytesIO(b'not-a-real-png'), 'broken.png'),
                (io.BytesIO(_png_bytes_with_color((0, 255, 255))), 'bad.jpg'),
            ]
        },
        content_type='multipart/form-data',
    )

    assert response.status_code == 200
    results = response.get_json()['results']
    assert results[0]['error'] == 'Malformed PNG image.'
    assert results[1]['error'] == 'Only PNG files are supported.'


def test_upload_chart_persists_decision_reason_and_feedback(client):
    response = client.post(
        '/api/charts',
        data={
            'ticker': 'AAPL',
            'date': '2026-02-15',
            'classification_label': 'yellow',
            'classification_red_pixels': '10',
            'classification_yellow_pixels': '123',
            'classification_decision_reason': 'yellow_dominant_by_ratio',
            'classification_marked_misclassified': 'true',
            'classification_feedback_note': 'overlay covered body',
            'chart': (io.BytesIO(_png_bytes_with_color((0, 255, 255))), 'aapl_20260215.png'),
        },
        content_type='multipart/form-data',
    )

    assert response.status_code == 201
    chart = response.get_json()['chart']
    assert chart['classification_decision_reason'] == 'yellow_dominant_by_ratio'
    assert chart['classification_marked_misclassified'] is True
    assert chart['classification_feedback_note'] == 'overlay covered body'

    charts = client.get('/api/charts/AAPL').get_json()['charts']
    assert charts[0]['classification_decision_reason'] == 'yellow_dominant_by_ratio'


def test_classifier_preview_reason_below_min_pixels(client):
    tiny = np.zeros((20, 20, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode('.png', tiny)
    assert ok
    response = client.post(
        '/api/classifier/preview',
        data={'image': (io.BytesIO(encoded.tobytes()), 'tiny.png')},
        content_type='multipart/form-data',
    )
    assert response.status_code == 200
    assert response.get_json()['decision_reason'] == 'below_min_pixels_none'
