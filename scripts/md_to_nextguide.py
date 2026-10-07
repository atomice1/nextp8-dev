#!/usr/bin/env python3
"""
md_to_nextguide.py - Convert Markdown files to Nextguide format

Takes Markdown files and converts them to the Nextguide format for use
with the Next computer's guide system.

Usage:
    python md_to_nextguide.py <input.md> <output.gde> [options]
    python md_to_nextguide.py <directory> <output.gde> [options]

The directory output combines all Markdown files into a single .gde file
containing multiple nodes (pages). The file can be up to 64KB.

Options:
  --author NAME     Set the author name
  --copyright TEXT  Set the copyright text
  --date YYYY/MM/DD Set the date (defaults to today)
  --version VER     Set the version string
"""

import sys
import os
import re
import tempfile
import itertools
from pathlib import Path
from datetime import datetime

# Maximum line length for output
LINE_MAXLEN = 80

# Regex to strip Nextguide markup tags
# Matches: @{b}, @{ub}, @{i}, @{ui}, and @{"...\" link NODE_NAME}


try:
    import markdown
except ImportError:
    print("Error: markdown package not installed. Install with: pip install markdown", file=sys.stderr)
    sys.exit(1)

try:
    # Import the custom fenced_code extension that supports indented fences
    # Use absolute import with os.path to find the extensions directory
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    extensions_dir = os.path.join(script_dir, 'extensions')
    if extensions_dir not in sys.path:
        sys.path.insert(0, extensions_dir)
    from fenced_code import FencedCodeExtension
except ImportError:
    print("Error: custom fenced_code extension not found", file=sys.stderr)
    sys.exit(1)

try:
    from html.parser import HTMLParser
except ImportError:
    print("Error: html.parser not available", file=sys.stderr)
    sys.exit(1)

try:
    import argparse
except ImportError:
    print("Error: argparse not available", file=sys.stderr)
    sys.exit(1)


class OutputNode:
    """Node in the output tree."""

    def __init__(self, node_type, content=None, children=None, context=None):
        """
        Args:
            node_type: The HTML element/tag name ('p', 'ul', 'ol', 'li', 'strong', etc.)
            content: String for leaf nodes (text content)
            children: List of child OutputNode for container nodes
            context: Dict of context-specific data (e.g., list ordinal, table rows)
        """
        self.node_type = node_type
        self.content = content  # None for containers, string for leaf nodes
        self.children = children or []
        self.context = context or {}


class OutputFormatter:
    """Format an OutputNode tree to Nextguide format."""

    def __init__(self, node_names=None):
        self.node_names = node_names or set()

    def _strip_markup(self, text):
        """Remove Nextguide markup tags from text for width calculations.

        For inline elements like @{"Installation" link INSTALL}, returns just "Installation".
        For formatting tags like @{b}text@{ub}, returns just "text".
        """
        # First, handle link tags: @{"text" link NODE_NAME}
        # Extract just the text part
        def extract_link_text(match):
            content = match.group(0)
            # Extract text between quotes
            quote_match = re.search(r'"([^"]*)"', content)
            if quote_match:
                return quote_match.group(1)
            return ''

        # Replace link tags with just the link text
        text = re.sub(r'@\{"[^"]*"\s*link\s*\w+\}', extract_link_text, text)

        # Then strip remaining simple markup tags like @{b}, @{ub}, @{i}, @{ui}
        return re.sub(r'@\{[a-z]+\}', '', text)

    def _hard_wrap_token(self, token, max_width):
        """Hard-wrap a token that exceeds max_width.

        Splits the token at max_width visible characters, preserving markup tags.
        Returns (chunk, remaining) where chunk is the first max_width chars and
        remaining is what's left.
        """
        if len(token) <= max_width:
            return token, ''

        # Count visible characters while preserving markup
        visible_count = 0
        i = 0
        while i < len(token) and visible_count < max_width:
            if token[i] == '@' and i + 1 < len(token) and token[i+1] == '{':
                # Markup tag - find the end and include it
                end_tag = token.find('}', i)
                if end_tag != -1:
                    i = end_tag + 1
                    continue
            i += 1
            visible_count += 1

        chunk = token[:i]
        remaining = token[i:]
        return chunk, remaining

    def _wrap_line(self, line, line_maxlen=LINE_MAXLEN, indent=0):
        """Wrap a line to the specified maximum length.

        Returns a list of lines. The first line starts at column 0,
        continuation lines are indented by `indent` spaces.

        Args:
            line: The line to wrap
            line_maxlen: Maximum line length (default 80)
            indent: Number of spaces to indent continuation lines (default 0)
        """
        if not line:
            return []

        # Calculate the effective max width for continuation lines
        cont_maxlen = line_maxlen - indent if indent > 0 else line_maxlen

        # If line fits (excluding markup), return as-is
        if len(self._strip_markup(line)) <= line_maxlen:
            return [line]

        # Split into words, handling NextGuide markup
        result = []

        # Tokenize the line into words (including markup tags as separate tokens)
        # Handle link format @{"text" link NODE_NAME} as a single token
        tokens = re.findall(r'@\{".*?"\s*link\s*\w+\}|\S+|\s+', line)

        current_line = ''
        current_width = 0

        for token in tokens:
            if token.isspace():
                # This is a space - we'll add it if the next word fits
                continue

            # This is a word (possibly containing markup)
            token_width = len(self._strip_markup(token))

            # Check if adding this word would exceed the limit
            space_needed = 1 if current_line else 0

            # Determine max width: if this is a continuation line, use reduced width
            max_width = cont_maxlen if result else line_maxlen

            if current_width + space_needed + token_width <= max_width:
                # Add to current line
                if current_line:
                    current_line += ' ' + token
                    current_width += space_needed + token_width
                else:
                    current_line = token
                    current_width = token_width
            else:
                # Line is full - save it and start a new indented line
                if current_line:
                    result.append(current_line)

                # If the token itself is too long (hard-wrap needed), break it up
                if token_width > max_width:
                    # Token is longer than max_width - hard wrap
                    # We need to break the token into chunks
                    remaining = token
                    while len(remaining) > max_width:
                        # Find where to break (at max_width visible chars)
                        # We need to count visible chars while preserving markup
                        chunk, remaining = self._hard_wrap_token(remaining, max_width)
                        if chunk:
                            result.append(chunk)
                    # Add remaining part to new line
                    if remaining:
                        current_line = ' ' * indent + remaining
                        current_width = indent + len(self._strip_markup(remaining))
                else:
                    # Start new indented line with this word
                    # Continuation lines are indented by the specified amount
                    current_line = ' ' * indent + token
                    current_width = indent + token_width

        # Don't forget the last line
        if current_line:
            result.append(current_line)

        return result

    def _is_inline(self, node):
        """Check if a node is inline (doesn't start a new block)."""
        return node.node_type in ('text', 'strong', 'em', 'b', 'i', 'a', 'code')

    def _format_inline_list(self, nodes):
        """Format a list of inline nodes as a single string."""
        return ''.join(self._format_inline(node) for node in nodes)

    def _format_link_inline(self, node):
        """Format link inline content."""
        href = node.context.get('href', '')
        inline = self._format_inline_list(node.children)
        node_names = node.context.get('node_names', set())

        # For internal anchors, check if they reference a valid node
        if href.startswith('#'):
            # Extract just the node name (strip path components if present)
            path = Path(href.lstrip('#'))
            node_name = path.stem.upper()
            # Only convert to link if the node exists in node_names
            if node_name in node_names:
                return f'@{{"{inline}" link {node_name}}}'
            else:
                # Plain text for non-existent nodes
                return inline

        # For external links, convert to node name
        # Extract just the filename (strip path components), then strip .md extension and uppercase
        path = Path(href)
        node_name = path.stem.upper()
        if node_name.endswith('.MD'):
            node_name = node_name[:-3]
        return f'@{{"{inline}" link {node_name}}}'

    def _format_inline(self, node):
        """Format inline content."""
        if node.node_type == 'a':
            return self._format_link_inline(node)
        elif node.node_type in ('strong', 'b'):
            return '@{b}' + self._format_inline_list(node.children) + '@{ub}'
        elif node.node_type in ('em', 'i'):
            return '@{i}' + self._format_inline_list(node.children) + '@{ui}'
        elif node.node_type == 'code':
            # Code is inline, just output content
            return self._format_inline_list(node.children)
        elif node.node_type == 'text':
            return node.content
        else:
            return ''

    def _format_children(self, node, max_width=80):
        """Format the parsed tree to Nextguide format via recursive walk.

        Split into runs of inline and block nodes, adding blank lines between runs.
        Skip empty text nodes.
        """
        output_lines = []
        children = list(node.children)
        if not children:
            return output_lines

        # Filter out empty text nodes
        filtered_children = [c for c in children if not (c.node_type == 'text' and c.content == '')]
        if not filtered_children:
            return output_lines

        last_was_block = False
        for i, (is_inline, chunk) in enumerate(itertools.groupby(filtered_children, self._is_inline)):
            if i > 0:
                output_lines.append('')
            chunk_list = list(chunk)
            assert len(chunk_list) > 0
            if is_inline:
                inline_text = self._format_inline_list(chunk_list)
                wrapped_lines = self._wrap_line(inline_text, line_maxlen=max_width)
                output_lines.extend(wrapped_lines)
                last_was_block = False
            else:
                output_lines.extend(self._format_block_list(chunk_list, max_width=max_width))
                last_was_block = True
        # Add blank line at the end only if last chunk was a block
        if last_was_block:
            output_lines.append('')
        return output_lines

    def _format_block_list(self, blocks, max_width=80):
        """Format a list of block nodes, adding blank lines between them."""
        output_lines = []
        for i, block in enumerate(blocks):
            if i > 0:
                output_lines.append('')
            output_lines.extend(self._format_block(block, max_width))
        return output_lines

    def _format_block(self, node, max_width=80):
        """Recursively format a block node and its children."""
        if node.node_type == 'p':
            return self._format_paragraph(node, max_width)
        elif node.node_type == 'ul':
            return self._format_unordered_list(node, max_width)
        elif node.node_type == 'ol':
            return self._format_ordered_list(node, max_width)
        elif node.node_type == 'li':
            return self._format_list_item(node, max_width)
        elif node.node_type == 'h1':
            return self._format_heading(node, max_width, level=1)
        elif node.node_type == 'h2':
            return self._format_heading(node, max_width, level=2)
        elif node.node_type == 'h3':
            return self._format_heading(node, max_width, level=3)
        elif node.node_type == 'h4':
            return self._format_heading(node, max_width, level=4)
        elif node.node_type == 'h5':
            return self._format_heading(node, max_width, level=5)
        elif node.node_type == 'h6':
            return self._format_heading(node, max_width, level=6)
        elif node.node_type == 'pre':
            return self._format_pre(node, max_width)
        elif node.node_type == 'table':
            return self._format_table(node, max_width)
        else:
            # Unknown block type - output empty list
            return []

    def _format_paragraph(self, node, max_width):
        """Format paragraph with word wrapping."""
        lines = self._format_children(node, max_width=max_width)
        # Don't add trailing newline - blank lines are handled by _format_children
        return lines if lines else []

    def _format_unordered_list(self, node, max_width):
        """Format unordered list, calling format on each li child."""
        output_lines = []
        for child in node.children:
            if child.node_type == 'li':
                lines = self._format_list_item(child, max_width, ordinal=None)
                output_lines.extend(lines)
        return output_lines

    def _format_ordered_list(self, node, max_width):
        """Format ordered list with incrementing ordinals."""
        output_lines = []
        for child in node.children:
            if child.node_type == 'li':
                parent_ol = child.context.get('parent_ol')
                if parent_ol:
                    ordinal = parent_ol.context.get('ordinal', 0)
                else:
                    ordinal = 0

                lines = self._format_list_item(child, max_width, ordinal=ordinal)

                if parent_ol:
                    parent_ol.context['ordinal'] = ordinal + 1
                output_lines.extend(lines)
        return output_lines

    def _format_list_item(self, node, max_width, ordinal=None):
        """Format list item with appropriate prefix."""
        if ordinal is not None:
            prefix = f"{ordinal + 1}. "
        else:
            prefix = "- "

        inner_max_width = max_width - len(prefix)
        inner_lines = self._format_children(node, max_width=inner_max_width)

        if not inner_lines:
            return []

        result = []
        for i, line in enumerate(inner_lines):
            if i == 0:
                result.append(prefix + line)
            else:
                result.append(' ' * len(prefix) + line)
        return result

    def _format_heading(self, node, max_width, level):
        """Format heading with centering."""
        inline = self._format_inline_list(node.children)
        wrapped_lines = self._wrap_line(inline, line_maxlen=max_width)

        marker = f"@{{c}}@{{h{level}}}"
        return [marker + line for line in wrapped_lines]

    def _format_pre(self, node, max_width):
        """Format preformatted text - truncate to max_width."""
        lines = []
        for child in node.children:
            if child.node_type == 'text':
                for line in child.content.split('\n'):
                    visible_len = len(self._strip_markup(line))
                    if visible_len > max_width:
                        truncated = line[:max_width]
                        lines.append(truncated)
                    else:
                        lines.append(line)
        return lines

    def _format_table(self, node, max_width):
        """Format table with column width calculation."""
        # Collect all rows
        rows = []
        for child in node.children:
            if child.node_type == 'tr':
                row = []
                for cell in child.children:
                    if cell.node_type in ('th', 'td'):
                        row.append(self._format_inline_list(cell.children))
                if row:
                    rows.append(row)

        if not rows:
            return []

        # Get number of columns
        num_cols = max(len(row) for row in rows) if rows else 0

        # Calculate column widths based on clean (markup-stripped) cell content
        col_widths = [0] * num_cols
        for row in rows:
            for i, cell in enumerate(row):
                clean_cell = self._strip_markup(cell)
                col_widths[i] = max(col_widths[i], len(clean_cell))

        # Helper to truncate a line to max visible characters
        def truncate_to_max_visible(line, max_width=LINE_MAXLEN):
            """Truncate line to max_width visible characters (excluding markup)."""
            visible_len = len(self._strip_markup(line))
            if visible_len <= max_width:
                return line
            # Truncate to max_width visible chars
            result = ''
            visible_count = 0
            i = 0
            while i < len(line) and visible_count < max_width:
                if line[i] == '@' and i + 1 < len(line) and line[i+1] == '{':
                    # Skip markup tag
                    end_tag = line.find('}', i)
                    if end_tag != -1:
                        result += line[i:end_tag+1]
                        i = end_tag + 1
                        continue
                result += line[i]
                visible_count += 1
                i += 1
            return result

        # Helper to format a row
        def format_row(cells, is_separator=False):
            """Format a row with vertical separators and padding."""
            line = ''
            for j, cell in enumerate(cells):
                if j > 0:
                    if is_separator:
                        line += ' + '
                    else:
                        line += ' | '
                if is_separator:
                    line += '-' * col_widths[j]
                else:
                    line += cell.ljust(col_widths[j])
            # Truncate if over max width
            return truncate_to_max_visible(line, LINE_MAXLEN)

        # Format all rows
        output_lines = []
        for i, row in enumerate(rows):
            if i == 0:
                # First row (header) - add separator after
                output_lines.append(format_row(row, is_separator=False))
                output_lines.append(format_row([''] * num_cols, is_separator=True))
            else:
                output_lines.append(format_row(row, is_separator=False))

        return output_lines


class NextguideHTMLParser(HTMLParser):
    """Parse HTML and convert to Nextguide format using a single stack of OutputNodes."""

    # Block-level HTML elements that should be separated by blank lines
    BLOCK_ELEMENTS = {'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li',
                      'pre', 'table', 'tr', 'th', 'td', 'blockquote', 'div'}

    def __init__(self, node_names=None):
        super().__init__()
        self.root = OutputNode('root', children=[])
        self.stack = [self.root]  # Stack of open OutputNodes
        self.node_names = node_names or set()  # Track node names for link conversion
        self.formatter = OutputFormatter(node_names=node_names)  # Formatter instance

    def _append_to_parent(self, node):
        """Append a node to its parent's children."""
        self.stack[-1].children.append(node)

    def _get_parent_ol_on_stack(self):
        """Find the nearest ol context on the stack (for li back-link)."""
        for node in reversed(self.stack):
            if node.node_type == 'ol':
                return node
        return None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            level = int(tag[1])
            new_node = OutputNode(tag, children=[], context={'level': level})
            self._append_to_parent(new_node)
            self.stack.append(new_node)
        elif tag == 'strong' or tag == 'b':
            new_node = OutputNode('strong', children=[])
            self._append_to_parent(new_node)
            self.stack.append(new_node)
        elif tag == 'em' or tag == 'i':
            new_node = OutputNode('em', children=[])
            self._append_to_parent(new_node)
            self.stack.append(new_node)
        elif tag == 'code':
            # Code is always inline (pre handles block formatting)
            # Since markdown generates <pre><code>...</code></pre> for blocks and <code>...</code> for inline,
            # we just skip code tags - they'll be stripped and output as plain text
            # Don't create a node, just don't do anything
            pass
        elif tag == 'a':
            href = attrs_dict.get('href', '')
            new_node = OutputNode('a', children=[], context={'href': href, 'node_names': self.node_names})
            self._append_to_parent(new_node)
            self.stack.append(new_node)
        elif tag == 'p':
            new_node = OutputNode('p', children=[])
            self._append_to_parent(new_node)
            self.stack.append(new_node)
        elif tag == 'ul':
            new_node = OutputNode('ul', children=[], context={'list_type': 'ul'})
            self._append_to_parent(new_node)
            self.stack.append(new_node)
        elif tag == 'ol':
            new_node = OutputNode('ol', children=[], context={'list_type': 'ol', 'ordinal': 0})
            self._append_to_parent(new_node)
            self.stack.append(new_node)
        elif tag == 'li':
            parent_ol = self._get_parent_ol_on_stack()
            if parent_ol:
                new_node = OutputNode('li', children=[], context={'parent_ol': parent_ol})
            else:
                new_node = OutputNode('li', children=[])
            self._append_to_parent(new_node)
            self.stack.append(new_node)
        elif tag == 'table':
            new_node = OutputNode('table', children=[], context={'rows': []})
            self._append_to_parent(new_node)
            self.stack.append(new_node)
        elif tag == 'tr':
            new_node = OutputNode('tr', children=[])
            self._append_to_parent(new_node)
            self.stack.append(new_node)
        elif tag in ('th', 'td'):
            new_node = OutputNode(tag, children=[])
            self._append_to_parent(new_node)
            self.stack.append(new_node)
        elif tag == 'pre':
            new_node = OutputNode('pre', children=[])
            self._append_to_parent(new_node)
            self.stack.append(new_node)

    def handle_data(self, data):
        # In HTML, consecutive whitespace is collapsed, but we need to preserve
        # newlines between block elements for blank lines
        if self.stack:
            import re
            # Split on newlines to handle blank lines between blocks
            # We'll process each line separately
            lines = data.split('\n')

            for i, line in enumerate(lines):
                # Collapse other whitespace in each line
                collapsed = re.sub(r'[ \t\r]+', ' ', line)
                if collapsed:
                    text_node = OutputNode('text', content=collapsed)
                    self.stack[-1].children.append(text_node)

    def handle_endtag(self, tag):
        if tag in ('p', 'ul', 'ol', 'li', 'strong', 'em', 'b', 'i', 'a',
                   'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'pre', 'table', 'tr', 'th', 'td'):
            if len(self.stack) > 1:
                node = self.stack.pop()

                # Add blank line after block elements (except li which is inside ul/ol)
                # This handles the case where there's whitespace between block elements
                if tag in ('p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'pre', 'table'):
                    # Add empty text node which will become a blank line
                    self.stack[-1].children.append(OutputNode('text', content=''))

                # Node is already appended to parent via _append_to_parent
                # It's just popped from the open stack

    def get_output(self):
        """Format the parsed tree to Nextguide format using OutputFormatter."""
        lines = self.formatter._format_children(self.root, max_width=LINE_MAXLEN)
        return '\n'.join(lines)


def markdown_to_nextguide(md_content, node_name="MAIN", title=None):
    """
    Convert Markdown content to Nextguide format.

    This function provides a standalone interface for testing and direct conversion.
    It performs the Markdown->HTML->Nextguide conversion with all formatting
    done within this module (word wrapping, line wrapping, etc.).

    Args:
        md_content: Markdown source text
        node_name: Name for the node (default: "MAIN")
        title: Override title (if None, extract from content)

    Returns:
        Nextguide formatted string with @node declaration
    """
    # Extract title from first H1 heading if not provided
    if title is None:
        title = extract_title(md_content)

    # Parse Markdown to HTML using Python-Markdown with custom fenced_code extension
    md = markdown.Markdown(extensions=['extra', FencedCodeExtension(), 'toc', 'tables'])
    html = md.convert(md_content)

    # Parse HTML and convert to Nextguide
    parser = NextguideHTMLParser(node_names={node_name})
    parser.feed(html)

    # Build node content
    output_lines = []
    output_lines.append('@node {}'.format(node_name))
    output_lines.append('')
    output_lines.append(parser.get_output())

    return '\n'.join(output_lines)


def extract_title(md_content):
    """Extract the first H1 heading from Markdown content."""
    # Parse to HTML first
    md = markdown.Markdown(extensions=['extra', 'tables'])
    html = md.convert(md_content)

    # Parse HTML to find H1
    class H1Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.h1_text = []
            self.in_h1 = False

        def handle_starttag(self, tag, attrs):
            if tag == 'h1':
                self.in_h1 = True

        def handle_endtag(self, tag):
            if tag == 'h1':
                self.in_h1 = False

        def handle_data(self, data):
            if self.in_h1:
                self.h1_text.append(data.strip())

    h1_parser = H1Parser()
    h1_parser.feed(html)

    if h1_parser.h1_text:
        return ' '.join(h1_parser.h1_text).strip()
    return "Markdown Document"


def generate_contents_node(node_names, node_titles):
    """Generate the CONTENTS node with a heading and list of links to each page.

    Args:
        node_names: List of node names in order
        node_titles: Dict mapping node_name -> title (from first H1 heading)

    Returns:
        CONTENTS node content string with @node declaration and link list
    """
    output_lines = []
    output_lines.append('@node CONTENTS')
    output_lines.append('')

    # Add heading: @{c}@{h1}Contents
    output_lines.append('@{c}@{h1}Contents')
    output_lines.append('')

    # Add list of links to each page
    for node_name in node_names:
        # Get title for this node (default to node name if not found)
        page_name = node_titles.get(node_name, node_name)
        # Format: - @{"<page name>" link <NODE_NAME>}
        output_lines.append(f'- @{{"{page_name}" link {node_name}}}')

    return '\n'.join(output_lines)


def markdown_to_node_content(md_content, node_name="MAIN", title=None, all_node_names=None, prev_node=None, next_node=None, add_toc=False):
    """
    Convert Markdown content to a single Nextguide node.

    Args:
        md_content: Markdown source text
        node_name: Name for the node
        title: Override title (if None, extract from content)
        all_node_names: Set of all node names for link conversion
        prev_node: Name of previous node (for @prev link)
        next_node: Name of next node (for @next link)
        add_toc: If True, add @toc CONTENTS after @node declaration

    Returns:
        Node content string with @node declaration, links, and heading
    """
    # Extract title from first H1 heading if not provided
    if title is None:
        title = extract_title(md_content)

    # Parse Markdown to HTML using Python-Markdown with custom fenced_code extension
    md = markdown.Markdown(extensions=['extra', FencedCodeExtension(), 'toc', 'tables'])
    html = md.convert(md_content)

    # Parse HTML and convert to Nextguide
    parser = NextguideHTMLParser(node_names=all_node_names or {node_name})
    parser.feed(html)

    # Build node content
    output_lines = []
    output_lines.append('@node {}'.format(node_name))

    # Add @toc CONTENTS if requested
    if add_toc:
        output_lines.append('@toc CONTENTS')

    # Add @prev and @next links if provided
    if prev_node:
        output_lines.append('@prev {}'.format(prev_node))
    if next_node:
        output_lines.append('@next {}'.format(next_node))

    output_lines.append('')
    output_lines.append(parser.get_output())

    return '\n'.join(output_lines)


def convert_markdown_file(input_path, output_path, metadata):
    """Convert a single Markdown file to Nextguide format."""
    with open(input_path, 'r', encoding='utf-8') as f:
        md_content = f.read()

    # Get node name from filename
    node_name = Path(input_path).stem.upper()

    # Limit node name to 15 characters
    if len(node_name) > 15:
        node_name = node_name[:15]

    # Get title from H1
    title = extract_title(md_content)

    # Create node content (no prev/next for single file)
    node_content = markdown_to_node_content(md_content, node_name, title, prev_node=None, next_node=None)

    # Build full .gde content
    result_lines = []

    # Add metadata commands at the top
    if metadata.get('author'):
        result_lines.append('@author {}'.format(metadata['author']))
    if metadata.get('copyright'):
        result_lines.append('@copyright {}'.format(metadata['copyright']))
    if metadata.get('date'):
        result_lines.append('@date {}'.format(metadata['date']))
    if metadata.get('version'):
        result_lines.append('@version {}'.format(metadata['version']))

    # Add the node content
    result_lines.append(node_content)

    full_content = '\n'.join(result_lines)

    # Write the final .gde file directly (no zxngdefmt post-processing needed)
    # Our _wrap_line() method already handles word wrapping
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_content)

    print(f"Converted: {input_path} -> {output_path}")


def convert_files(md_files, output_path, metadata):
    """Convert multiple Markdown files to a single Nextguide file.

    The first file is the first node, then CONTENTS, then remaining files.
    Links skip CONTENTS when navigating between nodes.
    """
    if not md_files:
        print(f"No Markdown files found")
        return

    # Collect all node names and titles
    node_names = []
    node_titles = {}

    for md_file in md_files:
        node_name = md_file.stem.upper()
        if len(node_name) > 15:
            node_name = node_name[:15]
        node_names.append(node_name)

        title = extract_title(md_file.read_text(encoding='utf-8'))
        node_titles[node_name] = title

    # Build full .gde content
    result_lines = []

    # Add metadata commands at the top
    if metadata.get('author'):
        result_lines.append('@author {}'.format(metadata['author']))
    if metadata.get('copyright'):
        result_lines.append('@copyright {}'.format(metadata['copyright']))
    if metadata.get('date'):
        result_lines.append('@date {}'.format(metadata['date']))
    if metadata.get('version'):
        result_lines.append('@version {}'.format(metadata['version']))

    # Process files: first file first, then CONTENTS, then remaining files
    for i, md_file in enumerate(md_files):
        node_name = node_names[i]

        # Determine prev/next, skipping CONTENTS node
        prev_node = node_names[i - 1] if i > 0 else None
        next_node = node_names[i + 1] if i < len(node_names) - 1 else None

        title = extract_title(md_file.read_text(encoding='utf-8'))
        node_content = markdown_to_node_content(
            md_file.read_text(encoding='utf-8'), node_name, title,
            set(node_names), prev_node, next_node, add_toc=True
        )

        result_lines.append('@-------------------------------------------------------------------------------')
        result_lines.append(node_content)

        # Add CONTENTS node after the first file
        if i == 0:
            contents_node = generate_contents_node(node_names, node_titles)
            result_lines.append('@-------------------------------------------------------------------------------')
            result_lines.append(contents_node)

    full_content = '\n'.join(result_lines)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_content)

    print(f"Converted {len(md_files)} files -> {output_path}")


def convert_directory(input_dir, output_path, metadata):
    """Convert all Markdown files in a directory to a single Nextguide file."""
    md_files = collect_md_files([input_dir])

    if not md_files:
        print(f"No Markdown files found in {input_dir}")
        return

    # Collect all node names and titles for link conversion and CONTENTS node
    node_names = []
    node_titles = {}  # Maps node_name -> title from first H1 heading

    for md_file in md_files:
        node_name = md_file.stem.upper()
        # Limit node name to 15 characters
        if len(node_name) > 15:
            node_name = node_name[:15]
        node_names.append(node_name)

        # Extract title from first H1 heading for CONTENTS node
        title = extract_title(md_file.read_text(encoding='utf-8'))
        node_titles[node_name] = title

    # Build full .gde content
    result_lines = []

    # Add metadata commands at the top
    if metadata.get('author'):
        result_lines.append('@author {}'.format(metadata['author']))
    if metadata.get('copyright'):
        result_lines.append('@copyright {}'.format(metadata['copyright']))
    if metadata.get('date'):
        result_lines.append('@date {}'.format(metadata['date']))
    if metadata.get('version'):
        result_lines.append('@version {}'.format(metadata['version']))

    # Process files: first file first, then CONTENTS, then remaining files
    for i, md_file in enumerate(md_files):
        node_name = node_names[i]

        # Determine prev/next, skipping CONTENTS node
        # Output order: first, CONTENTS, second, third, ...
        # Links point to adjacent files (skipping CONTENTS)
        prev_node = node_names[i - 1] if i > 0 else None
        next_node = node_names[i + 1] if i < len(node_names) - 1 else None

        title = extract_title(md_file.read_text(encoding='utf-8'))
        # Add @toc CONTENTS to each node
        node_content = markdown_to_node_content(md_file.read_text(encoding='utf-8'), node_name, title, set(node_names), prev_node, next_node, add_toc=True)

        # Add separator before each node
        result_lines.append('@-------------------------------------------------------------------------------')
        result_lines.append(node_content)

        # Add CONTENTS node after the first file
        if i == 0:
            contents_node = generate_contents_node(node_names, node_titles)
            result_lines.append('@-------------------------------------------------------------------------------')
            result_lines.append(contents_node)

    full_content = '\n'.join(result_lines)

    # Write the final .gde file directly (no zxngdefmt post-processing needed)
    # Our _wrap_line() method already handles word wrapping
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_content)

    print(f"Converted {len(md_files)} files: {input_dir} -> {output_path}")


def extract_links(md_content, base_dir):
    """Extract links from Markdown content and return list of (link_text, resolved_path).

    Resolves relative paths based on base_dir.
    """
    links = []

    # Match markdown links: [text](path)
    link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

    for match in link_pattern.finditer(md_content):
        text = match.group(1)
        path = match.group(2)

        # Skip anchor links
        if path.startswith('#'):
            continue

        # Resolve relative path
        resolved = (base_dir / path).resolve()

        links.append((text, resolved))

    return links


def collect_md_files(input_paths):
    """Collect all .md files from input paths, with link resolution.

    For each directory:
    - README.md first (if present)
    - Then other .md files, sorted alphabetically
    - Subdirectory files come after parent directory files

    Links are eagerly resolved - as each file is added, its linked files are
    also added (in order found) to the end of the list. Files are only added
    once (no duplicates).
    """
    md_files = []
    seen = set()  # Track resolved paths we've already seen

    def add_file(path):
        """Add a file if not already seen, and return True if added."""
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            md_files.append(path)
            return True
        return False

    def process_file(path):
        """Process a file: add it to list and look for links."""
        if not add_file(path):
            return

        # Look for links in this file and add them
        try:
            md_content = path.read_text(encoding='utf-8')
            base_dir = path.parent
            links = extract_links(md_content, base_dir)

            for text, resolved_path in links:
                if resolved_path.suffix == '.md' and resolved_path.exists():
                    # Add linked file (and its links) if not already seen
                    if resolved_path not in seen:
                        process_file(resolved_path)
        except Exception:
            # If we can't read the file, just continue
            pass

    for path_str in input_paths:
        path = Path(path_str)

        if path.is_file() and path.suffix == '.md':
            process_file(path)
        elif path.is_dir():
            # Directory - recursively find all .md files, then process their links
            def collect(directory):
                """Collect .md files from a directory, with README first."""
                # First, add README.md if present
                readme = directory / 'README.md'
                if readme.exists():
                    process_file(readme)

                # Then add other .md files in this directory, sorted
                other_md_files = sorted([f for f in directory.glob('*.md') if f != readme])
                for f in other_md_files:
                    process_file(f)

                # Then recurse into subdirectories, sorted
                subdirs = sorted([d for d in directory.iterdir() if d.is_dir()])
                for subdir in subdirs:
                    collect(subdir)

            collect(path)

    return md_files


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Convert Markdown files to Nextguide format.',
        add_help=False
    )
    parser.add_argument('input', nargs='+', help='Input Markdown file(s) or directory(ies)')
    parser.add_argument('output', help='Output .gde file path')
    parser.add_argument('--author', help='Author name')
    parser.add_argument('--copyright', help='Copyright text')
    parser.add_argument('--date', help='Date (YYYY/MM/DD format)')
    parser.add_argument('--version', help='Version string')
    parser.add_argument('--help', '-h', action='help', help='Show this help message')

    args = parser.parse_args()

    # Validate date if provided
    if args.date:
        try:
            datetime.strptime(args.date, '%Y/%m/%d')
        except ValueError:
            print("Error: Date must be in YYYY/MM/DD format", file=sys.stderr)
            sys.exit(1)

    return args


def main():
    args = parse_args()

    input_paths = args.input
    output_path = args.output

    # Build metadata dict
    metadata = {}
    if args.author:
        metadata['author'] = args.author
    if args.copyright:
        metadata['copyright'] = args.copyright
    if args.date:
        metadata['date'] = args.date
    else:
        # Default to today's date
        metadata['date'] = datetime.now().strftime('%Y/%m/%d')
    if args.version:
        metadata['version'] = args.version

    # Collect all md files from input paths
    md_files = collect_md_files(input_paths)

    if not md_files:
        print(f"Error: No Markdown files found", file=sys.stderr)
        sys.exit(1)

    if len(md_files) == 1:
        convert_markdown_file(str(md_files[0]), output_path, metadata)
    else:
        # Multiple files - convert as a combined guide
        convert_files(md_files, output_path, metadata)


if __name__ == '__main__':
    main()
