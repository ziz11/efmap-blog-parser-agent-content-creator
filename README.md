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
python3 parse_ef_blog.py
```

Offline/local mode (works without network):

```bash
python3 parse_ef_blog.py \
  --article-html post.html \
  --article-url https://ef-map.com/blog/ai-natural-language-commands-workers-ai
```

## Notes

- Keep real credentials in `.env` or `secrets.env` (both gitignored).
- Regenerated outputs overwrite:
  - `ef_map_blog_articles.md`
  - `ef_map_blog_articles.jsonl`
