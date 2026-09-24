import zipfile
import xml.etree.ElementTree as ET

import pytest

from backend.services.metadata_writer import _write_sync, build_comicinfo_xml
from conftest import make_cbz


def _comicinfo(path):
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.lower() == "comicinfo.xml"]
        assert len(names) == 1, zf.namelist()
        return ET.fromstring(zf.read(names[0]))


def test_build_comicinfo_xml_echappe_et_omet_les_vides():
    xml = build_comicinfo_xml({"Title": "Tintin & <Milou>", "Series": "", "Writer": None, "Year": 1946})
    root = ET.fromstring(xml)
    assert root.findtext("Title") == "Tintin & <Milou>"
    assert root.findtext("Year") == "1946"
    assert root.find("Series") is None and root.find("Writer") is None


def test_build_comicinfo_xml_ignore_les_champs_inconnus():
    assert "Pirate" not in build_comicinfo_xml({"Pirate": "x", "Title": "T"})


def test_ecriture_ajoute_comicinfo_et_garde_les_pages(tmp_path):
    f = make_cbz(tmp_path / "Akira - T01.cbz", pages=5)
    with zipfile.ZipFile(f) as zf:
        pages_avant = {n: zf.read(n) for n in zf.namelist()}

    _write_sync(str(f), {"Series": "Akira", "Number": "1", "Writer": "Katsuhiro Ōtomo"})

    assert _comicinfo(f).findtext("Writer") == "Katsuhiro Ōtomo"
    with zipfile.ZipFile(f) as zf:
        for name, data in pages_avant.items():
            assert zf.read(name) == data
            # Images déjà compressées : stockées telles quelles
            assert zf.getinfo(name).compress_type == zipfile.ZIP_STORED
    # Pas de fichier temporaire laissé à côté
    assert [p.name for p in tmp_path.iterdir()] == ["Akira - T01.cbz"]


def test_ecriture_remplace_un_comicinfo_existant(tmp_path):
    f = make_cbz(tmp_path / "a.cbz", comicinfo="<ComicInfo><Title>Ancien</Title></ComicInfo>")
    _write_sync(str(f), {"Title": "Nouveau"})
    _write_sync(str(f), {"Title": "Encore plus nouveau"})
    assert _comicinfo(f).findtext("Title") == "Encore plus nouveau"


def test_ecriture_refuse_les_non_cbz(tmp_path):
    f = tmp_path / "a.cbr"
    f.write_bytes(b"Rar!\x1a\x07\x00")
    with pytest.raises(ValueError):
        _write_sync(str(f), {"Title": "x"})
