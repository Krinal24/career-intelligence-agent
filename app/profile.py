import fitz


def extract_resume_text(pdf_path: str) -> str:
    document = fitz.open(pdf_path)

    pages = []

    for page in document:
        pages.append(page.get_text())

    document.close()

    return "\n".join(pages)


if __name__ == "__main__":
    text = extract_resume_text("data/Krinal Naghera.pdf")

    print(text[:5000])