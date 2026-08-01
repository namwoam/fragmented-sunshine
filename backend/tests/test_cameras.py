import click
import pytest
from click.testing import CliRunner

from vision.cameras import CAMERA_SOURCE, parse_camera_source

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", 0),
        (" 12 ", 12),
        (3, 3),
        ("http://laptop:8090/tray.mjpg", "http://laptop:8090/tray.mjpg"),
        ("rtsp://laptop/tray", "rtsp://laptop/tray"),
    ],
)
def test_parse_camera_source(value, expected):
    assert parse_camera_source(value) == expected


def test_click_camera_source_accepts_stream_url():
    @click.command()
    @click.option("--camera", type=CAMERA_SOURCE, required=True)
    def command(camera):
        click.echo(f"{type(camera).__name__}:{camera}")

    result = CliRunner().invoke(command, ["--camera", "http://laptop:8090/tray.mjpg"])

    assert result.exit_code == 0
    assert result.output == "str:http://laptop:8090/tray.mjpg\n"


def test_click_camera_source_rejects_empty_value():
    @click.command()
    @click.option("--camera", type=CAMERA_SOURCE, required=True)
    def command(camera):
        click.echo(camera)

    result = CliRunner().invoke(command, ["--camera", ""])

    assert result.exit_code == 2
    assert "camera source cannot be empty" in result.output
