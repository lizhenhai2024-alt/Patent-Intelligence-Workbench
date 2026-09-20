import pytest

from app.release.versioning import parse_release_version


def test_rc_version_maps_to_release_tag():
    result = parse_release_version("1.0.0rc1")

    assert result.version == "1.0.0rc1"
    assert result.tag == "v1.0.0-rc.1"
    assert result.prerelease is True


def test_stable_version_maps_to_stable_tag():
    result = parse_release_version("1.2.3")

    assert result.tag == "v1.2.3"
    assert result.prerelease is False


@pytest.mark.parametrize("value", ["1.0", "v1.0.0", "1.0.0-beta1", ""])
def test_unsupported_version_is_rejected(value):
    with pytest.raises(ValueError):
        parse_release_version(value)
