"""Generate a deterministic scanned/image-only PDF with no text layer for testing."""

import argparse
import io
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageDraw


def generate_scanned_pdf(output_path: Path) -> None:
    """Create a PDF containing only rasterized bitmap image data (no text layer)."""
    width, height = 612, 792  # Standard US Letter points

    # Render rasterized text onto a blank RGB canvas (scale 2x for clarity)
    img_width, img_height = width * 2, height * 2
    image = Image.new("RGB", (img_width, img_height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    # Draw deterministic scanned-like content
    draw.text(
        (80, 80),
        "This is an image-only scanned document.\nIt contains no searchable text layer.",
        fill=(0, 0, 0),
    )

    # Save image to PNG in memory
    img_buffer = io.BytesIO()
    image.save(img_buffer, format="PNG")
    img_bytes = img_buffer.getvalue()

    # Create PDF and insert image across full page rect
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    page.insert_image(page.rect, stream=img_bytes)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    doc.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate scanned test PDF fixture.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent.parent
        / "tests"
        / "fixtures"
        / "sample_scanned.pdf",
        help="Path where the generated PDF will be saved.",
    )
    args = parser.parse_args()

    generate_scanned_pdf(args.output)
    print(f"Generated scanned PDF fixture at {args.output}")

    # Verification: assert text extraction yields zero characters
    doc = fitz.open(str(args.output))
    extracted = "".join(page.get_text() for page in doc).strip()
    char_count = len(extracted)
    doc.close()

    print(f"Extracted characters: {char_count}")
    if char_count != 0:
        raise RuntimeError(f"Expected 0 extractable characters, got {char_count}")


if __name__ == "__main__":
    main()
