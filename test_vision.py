from google.cloud import vision


def detect_text(path: str) -> None:
    client = vision.ImageAnnotatorClient()

    with open(path, "rb") as image_file:
        content = image_file.read()

    image = vision.Image(content=content)
    response = client.text_detection(image=image)

    if response.error.message:
        raise RuntimeError(response.error.message)

    if not response.text_annotations:
        print("No text found.")
        return

    print(response.text_annotations[0].description)


if __name__ == "__main__":
    detect_text("test.jpg")
