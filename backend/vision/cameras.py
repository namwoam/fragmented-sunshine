import click


def parse_camera_source(value: str | int) -> str | int:
    """Convert numeric camera sources to indices while preserving stream URLs."""
    if isinstance(value, int):
        return value
    normalized = value.strip()
    return int(normalized) if normalized.isdigit() else normalized


class CameraSourceType(click.ParamType):
    name = "camera index or stream URL"

    def convert(self, value, param, ctx):
        if isinstance(value, int):
            return value
        if not isinstance(value, str) or not value.strip():
            self.fail("camera source cannot be empty", param, ctx)
        return parse_camera_source(value)


CAMERA_SOURCE = CameraSourceType()
