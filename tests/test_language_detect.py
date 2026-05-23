from codectx.scanner.language_detect import detect_language, is_likely_test


def test_detect_java() -> None:
    assert detect_language("src/Foo.java") == "java"


def test_detect_cpp() -> None:
    assert detect_language("src/foo.cpp") == "cpp"
    assert detect_language("include/foo.hpp") == "cpp"
    assert detect_language("include/foo.h") == "cpp"


def test_detect_unsupported() -> None:
    assert detect_language("README.md") is None


def test_likely_test() -> None:
    assert is_likely_test("src/test/java/FooTest.java")
    assert is_likely_test("tests/foo_test.cpp")
