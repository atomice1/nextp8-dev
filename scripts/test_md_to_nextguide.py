#!/usr/bin/env python3
"""
Test suite for md_to_nextguide.py

Tests the conversion of Markdown to Nextguide format with various
formatting elements and line length scenarios.
"""

import sys
import os

# Add the scripts directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from md_to_nextguide import (
    NextguideHTMLParser,
    OutputFormatter,
    markdown_to_nextguide,
    generate_contents_node,
    LINE_MAXLEN,
)

# Create a formatter instance to access the formatting methods
_formatter = OutputFormatter()
strip_markup = _formatter._strip_markup
wrap_line = _formatter._wrap_line


def test_strip_markup():
    """Test removal of Nextguide markup tags."""
    assert strip_markup("hello @{b}world@{ub}") == "hello world"
    assert strip_markup("@{i}italic@{ui}") == "italic"
    assert strip_markup("@{b}@{i}bold italic@{ui}@{ub}") == "bold italic"
    assert strip_markup("plain text") == "plain text"


def test_wrap_line_short():
    """Test wrapping of short lines (should return as-is)."""
    # Lines under max length should not be wrapped
    result = wrap_line("short line", line_maxlen=80)
    assert result == ["short line"], f"Expected ['short line'], got {result}"
    
    # Line at exactly max length
    result = wrap_line("x" * 80, line_maxlen=80)
    assert result == ["x" * 80], f"Expected ['x' * 80], got {result}"
    
    # Line just under max length
    result = wrap_line("x" * 79, line_maxlen=80)
    assert result == ["x" * 79], f"Expected ['x' * 79], got {result}"


def test_wrap_line_long_no_indent():
    """Test wrapping of long lines with no indent (paragraphs)."""
    # Long line that needs wrapping with no indent
    text = "This is a long line that definitely exceeds the eighty character limit and needs to be wrapped properly"
    result = wrap_line(text, line_maxlen=80, indent=0)
    
    assert len(result) >= 2, f"Expected at least 2 lines, got {len(result)}"
    # First line should not have indent
    assert not result[0].startswith(' '), "First wrapped line should not have indent"
    # Subsequent lines should not have indent for paragraphs
    for line in result[1:]:
        assert not line.startswith(' '), f"Wrapped line should have no indent: {line}"

    assert ' '.join(result) == text, "Wrapped lines should preserve original content"


def test_wrap_line_long_with_indent():
    """Test wrapping of long lines with indent (list items)."""
    # Long line that needs wrapping with 3-space indent (for "1. ")
    text = "1. This is a long list item that exceeds the eighty character limit and needs wrapping"
    result = wrap_line(text, line_maxlen=80, indent=3)

    assert len(result) >= 2, f"Expected at least 2 lines, got {len(result)}"
    # First line should start with the prefix
    assert result[0].startswith("1. "), f"First line should start with '1. ': {result[0]}"
    # Subsequent lines should have indent to align with content
    for line in result[1:]:
        assert line.startswith('   '), f"Wrapped line should have 3-space indent: {line}"


def test_wrap_line_various_prefixes():
    """Test wrapping with various list prefixes."""
    # Test with "- " prefix (2 chars)
    text = "- This is a long list item with dash prefix that needs wrapping"
    result = wrap_line(text, line_maxlen=80, indent=2)
    assert result[0].startswith("- "), "First line should start with '- '"
    for line in result[1:]:
        assert line.startswith('  '), f"Wrapped line should have 2-space indent: {line}"

    # Test with "10. " prefix (4 chars)
    text = "10. This is a long list item with numbered prefix that needs wrapping"
    result = wrap_line(text, line_maxlen=80, indent=4)
    assert result[0].startswith("10. "), "First line should start with '10. '"
    for line in result[1:]:
        assert line.startswith('    '), f"Wrapped line should have 4-space indent: {line}"

    # Test with "100. " prefix (5 chars)
    text = "100. This is a long list item with large number prefix that needs wrapping"
    result = wrap_line(text, line_maxlen=80, indent=5)
    assert result[0].startswith("100. "), "First line should start with '100. '"
    for line in result[1:]:
        assert line.startswith('     '), f"Wrapped line should have 5-space indent: {line}"


def test_wrap_line_with_attributes():
    """Test wrapping ignores text attributes when calculating visible length."""
    # Line with many attributes but few visible chars - should NOT wrap
    text = "@{b}" * 20 + "hello" + "@{ub}" * 20  # 40 attributes, 5 visible chars
    result = wrap_line(text, line_maxlen=80)
    assert len(result) == 1, f"Short visible content should not wrap: {result}"
    assert "hello" in result[0]

    # Line with many attributes AND many visible chars - should wrap at visible boundary
    # Create a line with ~100 visible chars + attributes
    visible_text = "word " * 20  # ~100 visible chars
    text = "@{b}" + visible_text + "@{ub}"  # ~100 visible chars + attributes
    result = wrap_line(text, line_maxlen=80)
    # Should have at least 2 lines (wrapped)
    assert len(result) >= 2, f"Long visible content should wrap: {result}"
    # First line visible length should be ~80
    first_line_visible = len(strip_markup(result[0]))
    assert first_line_visible <= 80, f"First line visible length {first_line_visible} exceeds 80"


def test_generate_contents_node():
    """Test generation of CONTENTS node with heading and link list."""
    node_names = ["INTRO", "USAGE", "FAQ"]
    node_titles = {
        "INTRO": "Introduction",
        "USAGE": "How to Use",
        "FAQ": "Frequently Asked Questions"
    }
    
    contents = generate_contents_node(node_names, node_titles)
    
    # Check @node declaration
    assert "@node CONTENTS" in contents
    
    # Check heading
    assert "@{c}@{h1}Contents" in contents
    
    # Check link list format
    assert '- @{"Introduction" link INTRO}' in contents
    assert '- @{"How to Use" link USAGE}' in contents
    assert '- @{"Frequently Asked Questions" link FAQ}' in contents


def test_markdown_paragraphs():
    """Test conversion of simple paragraphs."""
    md = """# Test

This is a paragraph with some text.

This is another paragraph."""

    result = markdown_to_nextguide(md, "TEST")

    assert "@node TEST" in result
    # Paragraphs should have content without special prefix markers
    assert "This is a paragraph" in result
    assert "This is another paragraph" in result

    assert "This is a paragraph with some text.\n\nThis is another paragraph." in result, "Paragraphs are separated by a blank line"


def test_markdown_with_toc():
    """Test conversion with @toc CONTENTS added to each node."""
    from md_to_nextguide import markdown_to_node_content
    
    md = """# Test Page

Some content here."""

    result = markdown_to_node_content(md, "TEST", add_toc=True)

    assert "@node TEST" in result
    assert "@toc CONTENTS" in result
    assert "Some content here" in result


def test_markdown_headings():
    """Test conversion of headings."""
    md = """# Main Title

## Section 1

### Subsection

#### Sub-subsection"""
    
    result = markdown_to_nextguide(md, "TEST")
    
    assert "@node TEST" in result
    assert "@{h1}" in result
    assert "@{h2}" in result
    assert "@{h3}" in result
    assert "@{h4}" in result


def test_markdown_strong_emphasis():
    """Test conversion of bold and italic text."""
    md = """# Test

This has **bold text** and *italic text* and ***both***."""
    
    result = markdown_to_nextguide(md, "TEST")
    
    assert "@{b}" in result  # bold marker
    assert "@{ub}" in result  # unbold marker
    assert "@{i}" in result  # italic marker
    assert "@{ui}" in result  # unitalic marker
    assert "bold text" in result
    assert "italic text" in result
    assert "@{b}bold text@{ub}" in result
    assert "@{i}italic text@{ui}" in result


def test_markdown_strong_with_parens():
    """Test that bold text with parentheses is rendered correctly without extra spaces."""
    md = """# Test

**Break** (or **Esc**)"""

    result = markdown_to_nextguide(md, "TEST")

    # Should not have extra spaces around bold tags
    assert "@{b} " not in result
    assert " @{ub}" not in result
    assert "@{b}Break@{ub}" in result
    assert "@{b}Esc@{ub}" in result


def test_markdown_unordered_list():
    """Test conversion of unordered lists."""
    md = """# Test

- First item
- Second item
- Third item"""

    result = markdown_to_nextguide(md, "TEST")

    assert "- First item" in result
    assert "- Second item" in result
    assert "- Third item" in result

    # List items should have no indent and no blank lines betwen them.
    # We force zxngdefmt to preserve this formatting by disabling
    # reformatting + word-wrap in zxngdefmt.
    assert "- First item\n- Second item\n- Third item" in result


def test_markdown_ordered_list():
    """Test conversion of ordered lists."""
    md = """# Test

1. First item
2. Second item
3. Third item"""
    
    result = markdown_to_nextguide(md, "TEST")
    
    assert "1. First item" in result
    assert "2. Second item" in result
    assert "3. Third item" in result

    # List items should have no indent and no blank lines betwen them.
    # We force zxngdefmt to preserve this formatting by disabling
    # reformatting + word-wrap in zxngdefmt.
    assert "1. First item\n2. Second item\n3. Third item" in result


def test_markdown_long_unordered_list():
    """Test conversion of long unordered list items that need wrapping."""
    md = """# Test

- This is a very long list item that exceeds the eighty character limit and needs to be wrapped with proper indentation
- Short item
- Another long item that will wrap to multiple lines with aligned continuation"""

    result = markdown_to_nextguide(md, "TEST")

    # First item should wrap with alignment (no extra indent)
    # The continuation line should be aligned with the first non-bullet character
    lines = result.split('\n')
    # Find the first list item (starts with "-")
    first_item_lines = []
    for i, line in enumerate(lines):
        if line.startswith("- This is a very long list item"):
            first_item_lines.append(line)
            # Continuation lines start at column 2 (after "- ")
            j = i + 1
            while j < len(lines) and lines[j].startswith("  ") and not lines[j].startswith("- "):
                first_item_lines.append(lines[j])
                j += 1
            break

    assert len(first_item_lines) >= 2, "Long list item should wrap to multiple lines"
    # Continuation lines should start with 2 spaces (aligned with content after "- ")
    for line in first_item_lines[1:]:
        assert line.startswith("  "), f"Continuation line should have 2-space indent: {line}"


def test_markdown_long_ordered_list():
    """Test conversion of long ordered list items that need wrapping."""
    md = """# Test

1. This is a very long numbered list item that exceeds the eighty character limit and needs to be wrapped
2. Short item
3. Another long item that will wrap to multiple lines with proper alignment"""
    
    result = markdown_to_nextguide(md, "TEST")

    lines = result.split('\n')
    # Find the first numbered list item (no extra indent)
    first_item_lines = []
    for i, line in enumerate(lines):
        if line.startswith("1. This is a very long numbered list item"):
            first_item_lines.append(line)
            # Continuation lines start after "1. " (3 chars)
            j = i + 1
            while j < len(lines) and lines[j].startswith("   ") and not lines[j].startswith("1. "):
                first_item_lines.append(lines[j])
                j += 1
            break

    assert len(first_item_lines) >= 2, "Long list item should wrap to multiple lines"
    # Continuation lines should start with 3 spaces (aligned with content after "1. ")
    for line in first_item_lines[1:]:
        assert line.startswith("   "), f"Continuation line should have 3-space indent: {line}"


def test_markdown_links():
    """Test conversion of links."""
    md = """# Test

Check out [this link](#TEST2) for more info.

See [another link](#ANOTHER) as well."""

    result = markdown_to_nextguide(md, "TEST")

    # Internal anchors should be plain text (not converted to links)
    # The link text "this link" and "another link" should appear
    assert "this link" in result
    assert "another link" in result
    # No link markers for internal anchors that don't reference existing nodes
    assert "LINK" not in result


def test_markdown_tables():
    """Test conversion of tables."""
    md = """# Test

| Column 1 | Column 2 |
|----------|----------|
| Value 1  | Value 2  |
| Value 3  | Value 4  |"""
    
    result = markdown_to_nextguide(md, "TEST")
    
    # Tables should be converted (may be plain text or formatted)
    assert "Column 1" in result
    assert "Value 1" in result


def test_markdown_code_inline():
    """Test conversion of inline code."""
    md = """# Test

Use `code()` function for testing."""
    
    result = markdown_to_nextguide(md, "TEST")
    
    # Inline code should be present (as plain text)
    assert "code()" in result


def test_markdown_code_block():
    """Test conversion of code blocks."""
    md = """# Test

```python
def test():
    print("hello")
```"""
    
    result = markdown_to_nextguide(md, "TEST")

    # Code blocks should be present
    assert "def test" in result
    assert "print" in result
    assert "\ndef test" in result, "Code blocks should not be indented"


def test_markdown_blockquote():
    """Test conversion of blockquotes."""
    md = """# Test

> This is a blockquote
> with multiple lines"""
    
    result = markdown_to_nextguide(md, "TEST")

    # Blockquotes should be present
    assert "This is a blockquote" in result


def test_markdown_table_with_attributes():
    """Test that text attributes in table cells are handled correctly."""
    md = """# Test

| Key | Action |
|-----|--------|
| **Break** | Action one |
| *Italic* | Action two |
| **Bold** and *italic* | Combined |

"""

    result = markdown_to_nextguide(md, "TEST")

    # Table content should be present
    assert "Break" in result
    assert "Action one" in result
    assert "Italic" in result
    # Text attributes should not have extra spaces around them
    assert "@{b} " not in result
    assert " @{ub}" not in result
    assert "@{b}Break@{ub}" in result


def test_markdown_table_truncation():
    """Test that long table lines are truncated based on visible characters."""
    # Create a table with long content that exceeds 80 visible chars
    md = """# Test

| Column A | Column B which is very long and will be truncated to eighty visible characters |
|----------|--------------------------------------------------------------------------------|
| Value 1  | This is a very long value that will exceed the eighty character limit         |

"""

    result = markdown_to_nextguide(md, "TEST")

    # Table should be present
    assert "Column A" in result
    assert "Value 1" in result
    # Visible content should be truncated at 80 chars (excluding attributes)
    lines = result.split('\n')
    for line in lines:
        # Check that visible chars (excluding markup) don't exceed 80
        visible = strip_markup(line)
        if line.strip() and not line.startswith('@node') and not line.startswith('@{'):
            assert len(visible) <= 80, f"Line exceeds 80 visible chars: {visible}"


def test_markdown_code_block_truncation():
    """Test that code blocks are truncated based on visible characters."""
    md = """# Test

```python
def very_long_function_name_that_exceeds_the_eighty_character_limit():
    x = "this is a very long string that will be truncated"
    return x
```

"""

    result = markdown_to_nextguide(md, "TEST")

    # Code block content should be present
    assert "def" in result
    assert "very_long_function_name" in result
    # Code blocks should not have 2-space indent
    assert "\n  def" not in result
    # Truncated lines should be within limits
    lines = result.split('\n')
    for line in lines:
        visible = strip_markup(line)
        if line.strip() and not line.startswith('@node') and not line.startswith('@{'):
            assert len(visible) <= 80, f"Code block line exceeds 80 visible chars: {visible}"


def test_empty_content():
    """Test handling of empty content."""
    result = markdown_to_nextguide("", "EMPTY")

    assert "@node EMPTY" in result


def test_special_characters():
    """Test handling of special characters."""
    md = """# Test

Special chars: $ % ^ & * ( ) [ ] { } | \\ / ? < > ~ `"""

    result = markdown_to_nextguide(md, "TEST")

    # Special characters should be preserved
    assert "$" in result
    assert "%" in result

def test_snippet1():
    md = """## Getting Started

- [Installation](install.md) - How to install nextp8 on your ZX Spectrum Next
- [Quick Start](#quick-start) - What to do after that

## Using nextp8

### Screens

nextp8 has three main screens that you'll use:

1. **Browse Screen** - File manager and cart launcher
    - [Browse Screen Guide](browse.md)
   
2. **Editor Screen** - Integrated development environment
    - [Editor Guide](editor.md)
    - Includes: Code, Sprite, Map, SFX, and Music editors
   
3. **REPL Screen** - Interactive Lua interpreter
    - [REPL Guide](repl.md)"""

    result = markdown_to_nextguide(md, "TEST")

    print(result)

    assert "@{c}@{h2}Getting Started" in result, "## converted to centered h2"
    assert '- @{"Installation" link INSTALL} - How to install nextp8 on your ZX Spectrum Next' in result, "Link to other Markdown page converted to Nextguide link"
    assert not '\nNext\n' in result, "Link should not be wrapped as its only 63 *visible* characters once Nextguide markup is removed"
    assert not '@{"link" link quick-start}' in result, "Link to internal anchor NOT converted to Nextguide link"
    assert not '@{"Quick Start" link quick-start}' in result, "Link to internal anchor NOT converted to Nextguide link"
    assert not '@{"Quick Start" link QUICK-START}' in result, "Link to internal anchor NOT converted to Nextguide link"
    assert not '@{"Quick Start" link QUICK_START}' in result, "Link to internal anchor NOT converted to Nextguide link"
    assert not '- Quick Start  - What to do after that' in result, "No double space after link"
    assert '- Quick Start - What to do after that' in result, "Link to internal anchor NOT converted to Nextguide link"
    assert '@{"link" link quick-start}nextp8 has three main screens that you\'ll use:' not in result, "No spurious link in the middle of unmarked-up paragraph text"
    assert "nextp8 has three main screens that you'll use:" in result, "No spurious link in the middle of unmarked-up paragraph text"
    assert "1. @{b} Browse Screen@{ub}  - File manager and cart launcher" not in result, "No extraneous spacing added after @{b} and @{ub}"
    assert "1. @{b}Browse Screen@{ub} - File manager and cart launcher" in result, "Bold text markdown convert to bold text attribute"
    assert "\n\n1. @{b}Browse Screen@{ub} - File manager and cart launcher" in result, "Blank line before list"
    assert "2.   Browse Screen Guide" not in result, "Sublist is not promoted to top-level list item"
    assert "2. Browse Screen Guide" not in result, "Sublist is not promoted to top-level list item"
    assert '2. @{"Browse Screen Guide" link BROWSE}' not in result, "Sublist is not promoted to top-level list item"
    assert '   - @{"Browse Screen Guide" link BROWSE}' in result, "Unordered sublist indented inside ordered list"
    assert '1. @{b}Browse Screen@{ub} - File manager and cart launcher\n   \n   - @{"Browse Screen Guide" link BROWSE}\n   \n2. @{b}Editor Screen@{ub} - Integrated development environment' in result, "Blank line before and after sublist"
    assert "3.  @{b} Editor Screen@{ub}  - Integrated development environment" not in result, "Sublist items don't affect parent numbering"
    assert "3. @{b}Editor Screen@{ub} - Integrated development environment" not in result, "Sublist items don't affect parent numbering"
    assert '2. @{b}Editor Screen@{ub} - Integrated development environment' in result, "Sublist items don't affect parent numbering"
    assert '   - Includes: Code, Sprite, Map, SFX, and Music editors' in result, "Unordered sublist indented inside ordered list"
    assert '\n   - @{"Editor Guide" link EDITOR}\n   - Includes: Code, Sprite, Map, SFX, and Music editors\n' in result, "No blank line between list items"
    assert """@{c}@{h2}Getting Started

- @{"Installation" link INSTALL} - How to install nextp8 on your ZX Spectrum Next
- Quick Start - What to do after that

@{c}@{h2}Using nextp8

@{c}@{h3}Screens

nextp8 has three main screens that you'll use:

1. @{b}Browse Screen@{ub} - File manager and cart launcher
   
   - @{"Browse Screen Guide" link BROWSE}
   
2. @{b}Editor Screen@{ub} - Integrated development environment
   
   - @{"Editor Guide" link EDITOR}
   - Includes: Code, Sprite, Map, SFX, and Music editors
   
3. @{b}REPL Screen@{ub} - Interactive Lua interpreter
   
   - @{"REPL Guide" link REPL}""" in result

def test_wrap_boundary():
    md = """# Heading 1

01234567890123456789 1234567890123456789 123456789 1234567890123456789 123456789

# Heading 2"""

    result = markdown_to_nextguide(md, "TEST")

    assert "\n01234567890123456789 1234567890123456789 123456789 1234567890123456789 123456789\n" in result, "80 character line with spaces not wrapped"

    md = """# Heading 1

01234567890123456789012345678901234567890123456789012345678901234567890123456789

# Heading 2"""

    result = markdown_to_nextguide(md, "TEST")

    assert "\n01234567890123456789012345678901234567890123456789012345678901234567890123456789\n" in result, "80 character line without spaces not wrapped"

    md = """# Heading 1

0123456789012345678901234567890123456789012345678901234567890123456789012345 67890

# Heading 2"""

    result = markdown_to_nextguide(md, "TEST")

    assert "\n0123456789012345678901234567890123456789012345678901234567890123456789012345\n67890\n" in result, "81 character line wrapped at last space before 80 character boundary"

    md = """# Heading 1

012345678901234567890123456789012345678901234567890123456789012345678901234567890

# Heading 2"""

    result = markdown_to_nextguide(md, "TEST")

    assert "\n01234567890123456789012345678901234567890123456789012345678901234567890123456789\n0\n" in result, "81 character line with no spaces hard-wrapped at 80 character boundary"

    md = """# Heading 1

[Installation](install.md) - 01234567890123456789 1234567890123456789 123456789 12345678901234

# Heading 2"""

    result = markdown_to_nextguide(md, "TEST")

    assert '\n@{"Installation" link INSTALL} - 01234567890123456789 1234567890123456789 123456789 12345678901234\n' in result, "80 *visible* character line not wrapped"

    md = """# Heading 1
    
[Installation](install.md) - 01234567890123456789 1234567890123456789 123456789 123456789012345

# Heading 2"""

    result = markdown_to_nextguide(md, "TEST")

    assert '\n@{"Installation" link INSTALL} - 01234567890123456789 1234567890123456789 123456789\n123456789012345\n' in result, "81 *visible* character line wrapped at last space"

    md = """# Heading 1

- 01234567890123456789 1234567890123456789 123456789 1234567890123456789 1234567

# Heading 2"""

    result = markdown_to_nextguide(md, "TEST")

    assert "\n- 01234567890123456789 1234567890123456789 123456789 1234567890123456789 1234567\n" in result, "80 character line with spaces not wrapped"

    md = """# Heading 1
    
- 01234567890123456789 1234567890123456789 123456789 1234567890123456789 12345678

# Heading 2"""

    result = markdown_to_nextguide(md, "TEST")

    assert "\n- 01234567890123456789 1234567890123456789 123456789 1234567890123456789\n  12345678\n" in result, "81 character line with spaces wrapped at last space"

def test_code_blocks_in_list():

    md = """# Heading 1
    
1. A list item
2. A list item with code:

    ```lua
    some lua code
    some more lua code
    ```

3. Another list item"""

    result = markdown_to_nextguide(md, "TEST")

    assert "1. A list item\n" in result, "First list item"

    assert not "2. A list item with code: lua" in result, "Fenced code block is not treated as inline list itme text"
    assert "2. A list item with code:\n" in result, "Second list item"
    assert "3. Another list item\n" in result, "Another list item"
    assert "\n   some lua code\n   some more lua code\n" in result, "Preformatted code indented inside list item"
    assert "2. A list item with code:\n\n   some lua code\n   some more lua code\n\n\n3. Another list item", "blank spaces around preformatted code block"

def test_inline_code():
    md = """# Heading 1

Some inline `code text` inside a paragraph."""

    result = markdown_to_nextguide(md, "TEST")

    assert "\nSome inline code text inside a paragraph.\n" in result, "Inline code markup is stripped"
 
def test_code_blocks():

    md = """# Heading 1
    
    first line of a code block
    second line of a code block
    
# Heading 2"""

    result = markdown_to_nextguide(md, "TEST")

    assert "\nfirst line of a code block\nsecond line of a code block\n" in result, "Four space prefix stripped from code blocks"
    assert "\n\nfirst line of a code block\nsecond line of a code block\n\n" in result, "Blank lines around code blocks"

    md = """# Heading 1

```lua
first line of a code block
second line of a code block
```

# Heading 2"""

    result = markdown_to_nextguide(md, "TEST")

    assert "\nfirst line of a code block\nsecond line of a code block\n" in result, "Triple backticks treated as code block"
    assert not "\nlua\n" in result, "Language is stripped from triple backtick code blocks"
    assert "\n\nfirst line of a code block\nsecond line of a code block\n\n" in result, "Blank lines around code blocks"

def run_all_tests():
    """Run all tests."""
    test_strip_markup()
    test_wrap_line_short()
    test_wrap_line_long_no_indent()
    test_wrap_line_long_with_indent()
    test_wrap_line_various_prefixes()
    test_wrap_line_with_attributes()
    test_generate_contents_node()
    test_markdown_paragraphs()
    test_markdown_with_toc()
    test_markdown_headings()
    test_markdown_strong_emphasis()
    test_markdown_unordered_list()
    test_markdown_ordered_list()
    test_markdown_long_unordered_list()
    test_markdown_long_ordered_list()
    test_markdown_links()
    test_markdown_tables()
    test_markdown_code_inline()
    test_markdown_code_block()
    test_markdown_blockquote()
    test_markdown_table_with_attributes()
    test_markdown_table_truncation()
    test_markdown_code_block_truncation()
    test_empty_content()
    test_special_characters()
    test_snippet1()
    test_wrap_boundary()
    test_inline_code()
    test_code_blocks()
    test_code_blocks_in_list()

if __name__ == "__main__":
    run_all_tests()
