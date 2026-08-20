import io
import warnings
from typing import cast

from PIL import Image, UnidentifiedImageError

from app.core.errors import InvalidImageError
from app.domain.models import ImageFormat, InspectedImage


class PillowImageInspector:
    def inspect(self, content: bytes) -> InspectedImage:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as image:
                    result = InspectedImage(
                        format=cast(ImageFormat, image.format),
                        width=image.width,
                        height=image.height,
                        mode=image.mode,
                        frame_count=getattr(image, "n_frames", 1),
                    )
                    image.verify()
                    return result
        except (
            UnidentifiedImageError,
            OSError,
            SyntaxError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise InvalidImageError() from exc
