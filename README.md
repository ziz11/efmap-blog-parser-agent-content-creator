# EFMap Blog Parser And Agent Content Creator

Tools and outputs for extracting EF Map blog content into reusable Markdown/JSONL artifacts for agent-assisted content workflows.

## Files

- `parse_ef_blog.py`: main parser.
- `post.html`: local article HTML snapshot.
- `ef_map_blog_articles.md`: parsed markdown output.
- `ef_map_blog_articles.jsonl`: parsed structured output.
- `.env.example`: optional non-secret runtime config template.
- `secrets.env.example`: optional secrets template for publishing/agents.

## Usage

Online crawl mode:

```bash
python3 parse_ef_blog.py --retries 5 --timeout 20 --min-articles 20
```

Offline/local mode (works without network):

```bash
python3 parse_ef_blog.py \
  --article-html post.html \
  --article-url https://ef-map.com/blog/ai-natural-language-commands-workers-ai
```

TLS fallback (if SSL chain issues in local environment):

```bash
python3 parse_ef_blog.py --insecure --retries 8 --timeout 30 --min-articles 20
```

## Notes

- Keep real credentials in `.env` or `secrets.env` (both gitignored).
- Full crawl regenerates:
  - `ef_map_blog_articles.md`
  - `ef_map_blog_articles.jsonl`
- Local single-article mode writes to:
  - `ef_map_blog_single_article.md`
  - `ef_map_blog_single_article.jsonl`
  This protects full-crawl outputs from accidental overwrite.
- The parser now uses HTTP retries and fails if parsed article count is lower than `--min-articles` to avoid silently writing partial exports.
