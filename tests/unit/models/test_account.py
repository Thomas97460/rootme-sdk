from rootme_sdk.models.account import UserProfile


def test_user_profile_model() -> None:
    profile = UserProfile(1, "Example", 10, 1, rank=1, solved_challenges_count=5)
    assert profile.position == 1
    assert profile.username == "Example"
    assert profile.name == "Example"
    assert profile.rank == 1
    assert profile.solved_challenges_count == 5
    assert profile.data == {}
