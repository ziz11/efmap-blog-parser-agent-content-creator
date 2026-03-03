# EFMap Blog Parser And Agent Content Creator

This repository contains EF Map blog parsing utilities and generated content artifacts for agent-assisted publishing workflows.

## Files

- `parse_ef_blog.py`: parser/extractor script.
- `post.html`: source HTML snapshot used for parsing.
- `ef_map_blog_articles.md`: parsed articles in Markdown output format.
- `ef_map_blog_articles.jsonl`: parsed articles in JSONL output format.

## Typical Flow

1. Run full crawl (recommended for production dataset):
   - `python3 parse_ef_blog.py --retries 5 --timeout 20 --min-articles 20`
2. If TLS validation fails locally, retry with:
   - `python3 parse_ef_blog.py --insecure --retries 8 --timeout 30 --min-articles 20`
3. Verify regenerated outputs in:
   - `ef_map_blog_articles.md` (markdown content output)
   - `ef_map_blog_articles.jsonl` (structured record output)

## Single Article Mode

- Use `--article-html post.html` only for local/offline parsing.
- Single-article mode writes to:
  - `ef_map_blog_single_article.md`
  - `ef_map_blog_single_article.jsonl`
- It no longer overwrites full-crawl files by default.
