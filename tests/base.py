import io
import json
import os
import re

import pytest
from click.testing import CliRunner

from casparser import read_cas_pdf
from casparser.enums import CASFileType
from casparser.exceptions import CASParseError, IncorrectPasswordError


class BaseTestClass:
    """Common test cases for all available parsers."""

    ansi_cleaner = re.compile(r"\x1b\[([0-9,A-Z]{1,2}(;[0-9]{1,2})?(;[0-9]{3})?)?[m|K]?")

    @classmethod
    def setup_class(cls):
        cls.cams_file_name = os.getenv("CAMS_CAS_FILE")
        cls.new_cams_file_name = os.getenv("CAMS_CAS_FILE_NEW")
        cls.cams_summary_file_name = os.getenv("CAMS_CAS_SUMMARY")
        cls.kfintech_summary_file_name = os.getenv("KFINTECH_CAS_SUMMARY")
        cls.kfintech_file_name = os.getenv("KFINTECH_CAS_FILE")
        cls.new_kfintech_file_name = os.getenv("KFINTECH_CAS_FILE_NEW")
        cls.bad_file_name = os.getenv("BAD_CAS_FILE")
        cls.cams_password = os.getenv("CAMS_CAS_PASSWORD")
        cls.kfintech_password = os.getenv("KFINTECH_CAS_PASSWORD")
        cls.nsdl_file_name = os.getenv("NSDL_CAS_FILE_1")

        cls.pdf_files = [
            (cls.cams_file_name, cls.cams_password, 10, 14),
            (cls.new_cams_file_name, cls.cams_password, 14, 30),
            (cls.kfintech_file_name, cls.kfintech_password, 17, 30),
            (cls.new_kfintech_file_name, cls.kfintech_password, 14, 30),
        ]

    def read_pdf(self, filename, password, output="dict"):
        return read_cas_pdf(filename, password, output=output)

    def test_output_json(self):
        for filename, password, num_folios, _ in self.pdf_files:
            json_data = self.read_pdf(filename, password, output="json")
            data = json.loads(json_data)
            assert (
                len(data.get("folios", [])) == num_folios
            ), f"Expected : {num_folios} :: Got {len(data.get('folios', []))}"
            for folio in data["folios"]:
                assert isinstance(folio["PAN"], str) and len(folio["PAN"]) == 10
                for scheme in folio.get("schemes", []):
                    assert scheme["isin"] is not None
                    assert scheme["amfi"] is not None
                    assert scheme["advisor"] not in (None, "ARN")
            assert data.get("investor_info", {}).get("mobile") not in (None, "")
            assert data["cas_type"] == CASFileType.DETAILED.value

    def test_read_summary(self):
        summary_files = (
            (self.cams_summary_file_name, self.cams_password, 4, 6),
            (self.kfintech_summary_file_name, self.kfintech_password, 9, 13),
        )
        for filename, password, num_folios, num_schemes in summary_files:
            data = self.read_pdf(filename, password)
            assert len(data.folios) == num_folios
            schemes_found = 0
            for folio in data.folios:
                schemes_found += len(folio.schemes)
                for scheme in folio.schemes:
                    assert scheme.isin is not None
                    assert scheme.amfi is not None
            assert schemes_found == num_schemes
            assert data.investor_info.mobile not in (None, "")
            assert data.cas_type == CASFileType.SUMMARY.value

    def test_read_dict(self):
        from casparser.cli import cli

        runner = CliRunner()

        for pdf_file, pdf_password, _, num_schemes in self.pdf_files:
            args = [pdf_file, "-p", pdf_password, "-a"]
            result = runner.invoke(cli, args)
            assert result.exit_code == 0
            clean_output = self.ansi_cleaner.sub("", result.output)
            assert "Statement Period :" in clean_output
            assert re.search(rf"Matched\s+:\s+{num_schemes}\s+schemes", clean_output) is not None
            assert re.search(r"Error\s+:\s+0\s+schemes", clean_output) is not None

    def test_invalid_password(self):
        with pytest.raises(IncorrectPasswordError) as exc_info:
            self.read_pdf(self.cams_file_name, "")
        assert "Incorrect PDF password!" in str(exc_info)

    def test_invalid_file(self):
        with pytest.raises(CASParseError) as exc_info, io.BytesIO(b"test") as fp:
            self.read_pdf(fp, "")
        assert "Unhandled error while opening" in str(exc_info)

    def test_invalid_file_type(self):
        with pytest.raises(CASParseError) as exc_info:
            self.read_pdf(1, "")
        assert "Invalid input" in str(exc_info)
