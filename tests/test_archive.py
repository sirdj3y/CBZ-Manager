import io
import zipfile

import pytest

from backend.services.archive import stream_zip
from backend.services.archive_format import detect_archive_ext
from backend.services.archive_safety import (
    ArchiveTooLarge,
    BoundedTotalReader,
    check_entry_count,
    read_entry_bounded,
)
from conftest import make_cbz, make_pdf


@pytest.mark.parametrize(
    "head, ext_disque, attendu",
    [
        (b"PK\x03\x04rest", ".cbz", ".cbz"),
        (b"Rar!\x1a\x07\x01\x00", ".cbr", ".cbr"),
        # Fichier renommé en .cbz avant conversion, mais encore en RAR : le contenu prime
        (b"Rar!\x1a\x07\x00", ".cbz", ".cbr"),
        (b"%PDF-1.7", ".cbz", ".pdf"),
        # Contenu inconnu : on garde l'extension, l'appelant échouera avec son propre message
        (b"garbage!", ".CBZ", ".cbz"),
    ],
)
def test_detect_archive_ext(tmp_path, head, ext_disque, attendu):
    f = tmp_path / f"album{ext_disque}"
    f.write_bytes(head)
    assert detect_archive_ext(f) == attendu


def test_detect_archive_ext_fichiers_reels(tmp_path):
    assert detect_archive_ext(make_cbz(tmp_path / "a.cbr")) == ".cbz"
    assert detect_archive_ext(make_pdf(tmp_path / "b.cbz")) == ".pdf"


def test_detect_archive_ext_fichier_absent(tmp_path):
    assert detect_archive_ext(tmp_path / "absent.cbr") == ".cbr"


def test_read_entry_bounded_compte_les_octets_reels():
    assert read_entry_bounded(io.BytesIO(b"x" * 100), max_bytes=100) == b"x" * 100
    with pytest.raises(ArchiveTooLarge):
        read_entry_bounded(io.BytesIO(b"x" * 101), max_bytes=100)


def test_zip_bomb_taille_annoncee_mensongere(tmp_path):
    """Une entrée très compressible dépasse le plafond une fois décompressée, quelle que soit
    la taille (petite) du fichier sur disque."""
    f = tmp_path / "bomb.cbz"
    with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("page.jpg", b"\0" * (3 * 1024 * 1024))
    assert f.stat().st_size < 100_000
    with zipfile.ZipFile(f) as zf, zf.open("page.jpg") as entry:
        with pytest.raises(ArchiveTooLarge):
            read_entry_bounded(entry, max_bytes=1024 * 1024)


def test_check_entry_count():
    check_entry_count(3000)
    with pytest.raises(ArchiveTooLarge):
        check_entry_count(3001)


def test_bounded_total_reader_cumule():
    budget = BoundedTotalReader(max_total=10)
    budget.add(6)
    budget.add(4)
    with pytest.raises(ArchiveTooLarge):
        budget.add(1)


def test_stream_zip_ignore_les_fichiers_absents(tmp_path):
    a = tmp_path / "a.cbz"
    a.write_bytes(b"A" * 3_000_000)  # > seuil de flush, plusieurs chunks
    data = b"".join(stream_zip([("a.cbz", str(a)), ("absent.cbz", str(tmp_path / "absent.cbz"))]))
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert zf.namelist() == ["a.cbz"]
        assert zf.read("a.cbz") == b"A" * 3_000_000
