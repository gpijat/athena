import pytest

from athena import atStatus


def test_status_greater_than():
    assert atStatus.ERROR > atStatus.SUCCESS


def test_status_lesser_than():
    assert atStatus.SUCCESS < atStatus.ERROR


def test_status_equal():
    custom_fail_status = atStatus.FailStatus('Custom_Fail_Status', (0, 255, 0), 100)
    custom_success_status = atStatus.SuccessStatus('Custom_Success_Status', (255, 0, 0), 100)
    
    assert custom_fail_status == custom_success_status


def test_custom_status_is_registered():
    custom_fail_status = atStatus.FailStatus('Custom_Fail_Status', (255, 0, 0), 100)

    assert custom_fail_status in atStatus.get_all_statuses()


def test_lowest_fail_status_lower_than_highest():
    assert atStatus.lowest_fail_status() < atStatus.highest_fail_status()


def test_lowest_success_status_lower_than_highest():
    assert atStatus.lowest_success_status() < atStatus.highest_success_status()


def test_get_status_by_name():
    assert atStatus.get_status_by_name('Default') is atStatus._DEFAULT


def test_all_fail_status_are_FailStatus_subclasses():
    assert all(isinstance(status, atStatus.FailStatus) for status in atStatus.get_all_fail_status())


def test_all_success_status_are_SuccessStatus_subclasses():
    assert all(isinstance(status, atStatus.SuccessStatus) for status in atStatus.get_all_success_status())

