from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

import numpy as np


def _load_chunks(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected a list of chunks in {path}")
    return [item if isinstance(item, dict) else {"text": str(item)} for item in payload]


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def _pca_2d(matrix: np.ndarray) -> np.ndarray:
    centered = matrix - matrix.mean(axis=0, keepdims=True)
    _u, _s, vt = np.linalg.svd(centered, full_matrices=False)
    return centered @ vt[:2].T


def _scale_points(points: np.ndarray, width: int, height: int, pad: int) -> list[tuple[float, float]]:
    if len(points) == 0:
        return []
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    span = np.maximum(maxs - mins, 1e-9)
    scaled = (points - mins) / span
    xs = pad + scaled[:, 0] * (width - 2 * pad)
    ys = height - pad - scaled[:, 1] * (height - 2 * pad)
    return list(zip(xs.tolist(), ys.tolist()))


def _chunk_label(chunk: dict[str, Any], index: int) -> str:
    title = str(chunk.get("title") or "").strip()
    pages = chunk.get("page_numbers") or []
    page_label = f" p.{','.join(map(str, pages))}" if pages else ""
    if title:
        return f"#{index}{page_label} {title}"
    text = str(chunk.get("text") or "").strip().replace("\n", " ")
    return f"#{index}{page_label} {text[:80]}"


def _chunk_preview(chunk: dict[str, Any], max_chars: int = 220) -> str:
    text = str(chunk.get("text") or "").strip().replace("\n", " ")
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


def _color(value: float) -> str:
    value = max(0.0, min(1.0, value))
    r = int(30 + 210 * value)
    g = int(85 + 65 * (1.0 - abs(value - 0.5) * 2))
    b = int(160 - 120 * value)
    return f"rgb({r},{g},{b})"


def _build_heatmap(similarity: np.ndarray, labels: list[str], limit: int) -> str:
    n = min(limit, similarity.shape[0])
    if n == 0:
        return ""
    cell = max(4, min(14, 640 // n))
    size = cell * n
    rects = []
    for row in range(n):
        for col in range(n):
            value = float(similarity[row, col])
            color = _color((value + 1.0) / 2.0)
            tip = html.escape(f"{labels[row]} x {labels[col]}: {value:.3f}")
            rects.append(
                f'<rect x="{col * cell}" y="{row * cell}" width="{cell}" height="{cell}" '
                f'fill="{color}"><title>{tip}</title></rect>'
            )
    return (
        f'<svg class="heatmap" width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        + "".join(rects)
        + "</svg>"
    )


def _build_scatter(points: np.ndarray, labels: list[str], chunks: list[dict[str, Any]]) -> str:
    width, height, pad = 820, 460, 42
    coords = _scale_points(points, width, height, pad)
    circles = []
    for index, (x, y) in enumerate(coords):
        label = html.escape(labels[index])
        preview = html.escape(_chunk_preview(chunks[index]))
        circles.append(
            f'<circle class="point" cx="{x:.2f}" cy="{y:.2f}" r="5" data-index="{index}">'
            f"<title>{label}\n{preview}</title></circle>"
        )
    return (
        f'<svg class="scatter" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<line x1="{pad}" y1="{height - pad}" x2="{width - pad}" y2="{height - pad}" />'
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height - pad}" />'
        + "".join(circles)
        + "</svg>"
    )


def _nearest_neighbors(similarity: np.ndarray, labels: list[str], top_n: int) -> list[dict[str, Any]]:
    rows = []
    for index in range(similarity.shape[0]):
        ranked = np.argsort(similarity[index])[::-1]
        ranked = [int(item) for item in ranked if int(item) != index][:top_n]
        rows.append(
            {
                "index": index,
                "label": labels[index],
                "neighbors": [
                    {
                        "index": other,
                        "label": labels[other],
                        "score": float(similarity[index, other]),
                    }
                    for other in ranked
                ],
            }
        )
    return rows


def _write_html(
    output: Path,
    embeddings_path: Path,
    chunks_path: Path,
    embeddings: np.ndarray,
    chunks: list[dict[str, Any]],
    similarity: np.ndarray,
    points: np.ndarray,
    heatmap_limit: int,
    neighbor_limit: int,
) -> None:
    labels = [_chunk_label(chunk, index) for index, chunk in enumerate(chunks)]
    neighbors = _nearest_neighbors(similarity, labels, neighbor_limit)
    heatmap = _build_heatmap(similarity, labels, heatmap_limit)
    scatter = _build_scatter(points, labels, chunks)

    neighbor_rows = []
    for row in neighbors:
        items = "".join(
            "<li>"
            f"<span>{html.escape(item['label'])}</span>"
            f"<strong>{item['score']:.3f}</strong>"
            "</li>"
            for item in row["neighbors"]
        )
        neighbor_rows.append(
            '<details class="neighbor-row">'
            f"<summary>{html.escape(row['label'])}</summary>"
            f"<ol>{items}</ol>"
            "</details>"
        )

    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Embedding Visualization</title>
  <style>
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      color: #202124;
      background: #f7f8fa;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 28px 22px 48px;
    }}
    h1, h2 {{
      margin: 0 0 12px;
      font-weight: 700;
      letter-spacing: 0;
    }}
    h1 {{ font-size: 28px; }}
    h2 {{ font-size: 20px; margin-top: 30px; }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 10px;
      margin: 18px 0 22px;
    }}
    .metric {{
      background: #fff;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      padding: 12px 14px;
    }}
    .metric span {{
      display: block;
      color: #5f6876;
      font-size: 12px;
      margin-bottom: 6px;
    }}
    .metric strong {{
      font-size: 18px;
      word-break: break-all;
    }}
    .panel {{
      background: #fff;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      padding: 16px;
      overflow: auto;
    }}
    .scatter line {{
      stroke: #aeb7c5;
      stroke-width: 1;
    }}
    .point {{
      fill: #176b87;
      opacity: 0.78;
      cursor: pointer;
    }}
    .point:hover {{
      fill: #d44f35;
      opacity: 1;
    }}
    .heatmap {{
      display: block;
      image-rendering: pixelated;
    }}
    .neighbor-row {{
      background: #fff;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      margin: 8px 0;
      padding: 10px 12px;
    }}
    summary {{
      cursor: pointer;
      font-weight: 700;
    }}
    li {{
      margin: 8px 0;
    }}
    li span {{
      display: inline-block;
      max-width: calc(100% - 72px);
      vertical-align: top;
    }}
    li strong {{
      float: right;
      color: #176b87;
    }}
    code {{
      background: #eef1f5;
      border-radius: 4px;
      padding: 2px 5px;
    }}
  </style>
</head>
<body>
<main>
  <h1>Embedding Visualization</h1>
  <div class="meta">
    <div class="metric"><span>Embeddings</span><strong>{html.escape(str(embeddings_path))}</strong></div>
    <div class="metric"><span>Chunks</span><strong>{html.escape(str(chunks_path))}</strong></div>
    <div class="metric"><span>Shape</span><strong>{embeddings.shape[0]} x {embeddings.shape[1]}</strong></div>
    <div class="metric"><span>Similarity Range</span><strong>{similarity.min():.3f} to {similarity.max():.3f}</strong></div>
  </div>
  <h2>PCA Scatter</h2>
  <div class="panel">{scatter}</div>
  <h2>Cosine Similarity Heatmap</h2>
  <div class="panel">{heatmap}</div>
  <h2>Nearest Neighbors</h2>
  {''.join(neighbor_rows)}
</main>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize cached chunk embeddings as a standalone HTML file.")
    parser.add_argument("--embeddings", required=True, help="Path to a cached .npy embedding matrix.")
    parser.add_argument("--chunks", required=True, help="Path to the chunks JSON matching the embedding rows.")
    parser.add_argument("--output", required=True, help="Path to write the HTML report.")
    parser.add_argument("--heatmap-limit", type=int, default=120)
    parser.add_argument("--neighbor-limit", type=int, default=5)
    args = parser.parse_args()

    embeddings_path = Path(args.embeddings)
    chunks_path = Path(args.chunks)
    output_path = Path(args.output)

    embeddings = np.load(embeddings_path).astype(np.float32)
    chunks = _load_chunks(chunks_path)
    if embeddings.ndim != 2:
        raise ValueError(f"Expected a 2D embedding matrix, got shape {embeddings.shape}")
    if embeddings.shape[0] != len(chunks):
        raise ValueError(
            f"Row count mismatch: {embeddings_path} has {embeddings.shape[0]} rows, "
            f"but {chunks_path} has {len(chunks)} chunks."
        )

    normalized = _normalize_rows(embeddings)
    similarity = normalized @ normalized.T
    points = _pca_2d(normalized)
    _write_html(
        output_path,
        embeddings_path,
        chunks_path,
        embeddings,
        chunks,
        similarity,
        points,
        max(1, args.heatmap_limit),
        max(1, args.neighbor_limit),
    )
    print(
        json.dumps(
            {
                "output": str(output_path),
                "embeddings": str(embeddings_path),
                "chunks": str(chunks_path),
                "shape": list(embeddings.shape),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
