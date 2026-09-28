from unittest.mock import patch
from app.jobs import job_ag_start_jobs

@patch('app.jobs.get_commands')
@patch('app.jobs.job_ag_create_job')
def test_job_ag_start_jobs(mock_create_job, mock_get_commands):
    # 모의 get_commands 반환 값 설정
    mock_get_commands.return_value = ['job1', 'job2']

    # job_ag_start_jobs 함수 실행
    job_ag_start_jobs()

    # get_commands가 호출되었는지 확인
    mock_get_commands.assert_called_once()
    # job_ag_create_job가 두 번 호출되었는지 확인
    assert mock_create_job.call_count == 2
    # job_ag_create_job이 올바른 인수로 호출되었는지 확인
    mock_create_job.assert_any_call('job1')
    mock_create_job.assert_any_call('job2')