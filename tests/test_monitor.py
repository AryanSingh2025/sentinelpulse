from backend.main import LogFileCursor, parse_line


def test_empty_file_has_no_events(tmp_path):
    log_file = tmp_path / "app.log"
    log_file.touch()

    assert LogFileCursor().read_new_lines(log_file) == []


def test_cursor_reads_only_new_appended_lines(tmp_path):
    log_file = tmp_path / "app.log"
    log_file.write_text("one\n", encoding="utf-8")
    cursor = LogFileCursor()

    assert cursor.read_new_lines(log_file) == ["one"]

    with log_file.open("a", encoding="utf-8") as stream:
        stream.write("two\n")

    assert cursor.read_new_lines(log_file) == ["two"]


def test_cursor_waits_for_a_partial_line_to_finish(tmp_path):
    log_file = tmp_path / "app.log"
    log_file.write_text("2026-09-28 12:00:00 INFO api partial", encoding="utf-8")
    cursor = LogFileCursor()

    assert cursor.read_new_lines(log_file) == []

    with log_file.open("a", encoding="utf-8") as stream:
        stream.write(" message\n")

    lines = cursor.read_new_lines(log_file)
    assert lines == ["2026-09-28 12:00:00 INFO api partial message"]
    assert parse_line(lines[0])["message"] == "partial message"


def test_cursor_resets_after_truncation(tmp_path):
    log_file = tmp_path / "app.log"
    log_file.write_text("old content that is longer\n", encoding="utf-8")
    cursor = LogFileCursor()
    cursor.read_new_lines(log_file)

    log_file.write_text("new\n", encoding="utf-8")

    assert cursor.read_new_lines(log_file) == ["new"]


def test_cursor_resets_when_log_is_replaced(tmp_path):
    log_file = tmp_path / "app.log"
    replacement = tmp_path / "rotated.log"
    log_file.write_text("old\n", encoding="utf-8")
    cursor = LogFileCursor()
    cursor.read_new_lines(log_file)

    replacement.write_text("new rotated record with a longer line\n", encoding="utf-8")
    replacement.replace(log_file)

    assert cursor.read_new_lines(log_file) == ["new rotated record with a longer line"]


def test_malformed_appended_line_does_not_raise(tmp_path):
    log_file = tmp_path / "app.log"
    log_file.write_text("malformed\n", encoding="utf-8")

    for line in LogFileCursor().read_new_lines(log_file):
        assert parse_line(line) is None
