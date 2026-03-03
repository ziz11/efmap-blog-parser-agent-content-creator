# EFMap Blog Parser And Agent Content Creator

This repository contains EF Map blog parsing utilities and generated content artifacts for agent-assisted publishing workflows.

## Files

- `parse_ef_blog.py`: parser/extractor script.
- `post.html`: source HTML snapshot used for parsing.
- `ef_map_blog_articles.md`: parsed articles in Markdown output format.
- `ef_map_blog_articles.jsonl`: parsed articles in JSONL output format.

## Typical Flow

1. Refresh or replace `post.html` with the latest source content.
2. Run `parse_ef_blog.py`.
3. Verify regenerated outputs in:
   - `ef_map_blog_articles.md` (markdown content output)
   - `ef_map_blog_articles.jsonl` (structured record output)
