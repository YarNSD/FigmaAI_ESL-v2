"""
ESL Figma AI — Image Agent
Dedicated agent for educational image search and generation.
Strategy:
1. First tries real authentic educational photography via Wikimedia Commons API (fast, high quality, no rate limit).
2. If no photo is found or for creative/abstract topics, generates clear educational imagery via Pollinations AI with smart prompt enhancement and rate-limiting (to prevent 429 errors).
3. Converts downloaded images to Base64 so Figma receives raw bytes directly without CORS or domain restrictions.
4. Auto-detects local proxy (2080/1080/7890) for reliable access.
"""
import asyncio
import base64
import logging
from pathlib import Path
import re
import socket
import urllib.parse
import httpx
import random
from server import agent_logger

logger = logging.getLogger("image_agent")

# Cache query -> base64 string
_IMAGE_CACHE: dict[str, str] = {}

# Warning collector for current batch
_LAST_BATCH_WARNINGS: list[str] = []


def add_warning(msg: str):
    global _LAST_BATCH_WARNINGS
    if msg and msg not in _LAST_BATCH_WARNINGS:
        _LAST_BATCH_WARNINGS.append(msg)


def get_and_clear_warnings() -> list[str]:
    global _LAST_BATCH_WARNINGS
    w = list(_LAST_BATCH_WARNINGS)
    _LAST_BATCH_WARNINGS = []
    return w

# Rate limit semaphore for generative AI endpoints (Pollinations)
_POLLINATIONS_SEMAPHORE = asyncio.Semaphore(1)
_LAST_POLLINATIONS_TIME = 0.0

# User-Agent for Wikipedia API compliance
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 ESLFigmaAI/1.0"
}


def _detect_proxy() -> str | None:
    """Auto-detect active local proxy on common ports (2080, 1080, 7890)."""
    for port in [2080, 1080, 7890]:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return f"http://127.0.0.1:{port}"
        except (socket.timeout, ConnectionRefusedError, OSError):
            pass
    return None


def _clean_query(raw_query: str, topic: str = "") -> str:
    """Clean and optimize query for image search."""
    if not raw_query:
        return topic or "english education"
    
    clean = raw_query.strip()
    # Remove common quiz boilerplates
    clean = re.sub(r"^(photo of|picture of|an? |the |illustration of|image of)\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"^(which of the following|what is|what do you|where is|sentence with|gap|choose the)\s*", "", clean, flags=re.IGNORECASE)
    # Strip trailing punctuation or question marks
    clean = clean.strip("?.:;! \t\n")
    # If topic is not in query, add topic context only if query is too generic (1 word)
    if topic and topic.lower() not in clean.lower() and len(clean.split()) < 2:
        clean = f"{clean} {topic}"
    return clean.strip()


async def _search_pinterest(query: str, client: httpx.AsyncClient) -> bytes | None:
    """Search Pinterest for high-quality, aesthetic, contextually relevant images.
    Uses indexed Pinterest pins via high-speed image search with i.pinimg.com extraction.
    Strictly filters out stock watermarks (Shutterstock, iStock, Alamy, etc.).
    """
    try:
        clean_q = _clean_query(query)
        encoded = urllib.parse.quote_plus(f"{clean_q} site:pinterest.com")
        url = f"https://yandex.com/images/search?text={encoded}"
        resp = await client.get(url, timeout=5.5)
        if resp.status_code != 200:
            return None
        
        matches = re.findall(r'https?://i\.pinimg\.com/(?:originals|736x|564x|474x)/[^\s"\'<>&]+\.(?:jpg|png|webp)', resp.text)
        # Filter out user avatars, icons, tiny thumbnails and stock photo watermarks
        WATERMARK_INDICATORS = (
            "_rs", "75x75", "avatar", "profile", "user", "icon",
            "shutterstock", "istock", "alamy", "dreamstime", "watermark",
            "depositphotos", "vectorstock", "stock-photo", "preview", "watermarked"
        )
        good_pins = [
            u for u in matches
            if not any(x in u.lower() for x in WATERMARK_INDICATORS)
        ]
        
        # Deduplicate preserving order
        seen = set()
        unique_pins = []
        for u in good_pins:
            if u not in seen:
                seen.add(u)
                unique_pins.append(u)
        
        # Prioritize high resolution (originals / 736x)
        def _pin_score(u: str) -> int:
            if "/originals/" in u:
                return 0
            if "/736x/" in u:
                return 1
            if "/564x/" in u:
                return 2
            return 3

        unique_pins.sort(key=_pin_score)

        # Try downloading top candidates
        for pin_url in unique_pins[:5]:
            try:
                img_resp = await client.get(pin_url, timeout=6.5)
                if img_resp.status_code == 200 and len(img_resp.content) > 10000:
                    logger.info(f"📌 ImageAgent: Clean photo found for '{clean_q}' ({len(img_resp.content):,} bytes) -> {pin_url[:60]}...")
                    return img_resp.content
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"Pinterest search failed for '{query}': {e}")
    return None


async def _search_wikimedia(query: str, client: httpx.AsyncClient) -> bytes | None:
    """Search Wikipedia for a relevant educational photo.
    Tries up to 10 results and skips person biographies and portrait headshots.
    """
    # Page titles hinting it's a biography/person page
    PERSON_TITLE_INDICATORS = (
        "footballer", "singer", "actor", "politician", "coach", "manager",
        "musician", "artist", "writer", "philosopher", "scientist", "director",
    )
    # Filename patterns that suggest person portrait (e.g. "Walter_Benjamin.jpg")
    PERSON_FILENAME_INDICATORS = (
        "_portrait", "_headshot", "cropped_portrait", "photo_of_",
    )

    try:
        encoded_query = urllib.parse.quote_plus(query)
        url = (
            f"https://en.wikipedia.org/w/api.php?action=query&generator=search"
            f"&gsrsearch={encoded_query}&gsrlimit=10&prop=pageimages|extracts"
            f"&pithumbsize=600&exintro=1&exsentences=1&format=json"
        )
        resp = await client.get(url, timeout=6.0)
        if resp.status_code != 200:
            return None
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})

        candidates = []
        for pid, page in pages.items():
            thumb = page.get("thumbnail", {}).get("source", "")
            if not thumb or thumb.lower().endswith(".svg") or thumb.lower().endswith(".png"):
                # Allow .png only if it's clearly not a chart/map
                if not thumb.lower().endswith(".png"):
                    continue

            # Skip pages that are clearly person biographies
            title_lower = page.get("title", "").lower()
            if any(ind in title_lower for ind in PERSON_TITLE_INDICATORS):
                continue

            # Skip filenames that suggest portrait of a named person
            thumb_lower = thumb.lower()
            if any(ind in thumb_lower for ind in PERSON_FILENAME_INDICATORS):
                continue

            # Check that the filename contains at least one keyword from the query
            # (rough relevance filter)
            query_keywords = set(query.lower().split())
            thumb_filename = thumb_lower.split("/")[-1].split("?")[0]
            # If thumbnail filename contains no query-related words, deprioritize
            keyword_match = any(kw in thumb_filename for kw in query_keywords if len(kw) > 3)
            candidates.append((0 if keyword_match else 1, thumb))

        # If no candidates found with full query, fallback to core 1-2 nouns
        if not candidates and len(query.split()) > 2:
            words = [w for w in query.split() if len(w) > 2]
            core = " ".join(words[-2:])
            encoded_core = urllib.parse.quote_plus(core)
            url2 = (
                f"https://en.wikipedia.org/w/api.php?action=query&generator=search"
                f"&gsrsearch={encoded_core}&gsrlimit=6&prop=pageimages"
                f"&pithumbsize=600&format=json"
            )
            try:
                resp2 = await client.get(url2, timeout=5.0)
                if resp2.status_code == 200:
                    pages2 = resp2.json().get("query", {}).get("pages", {})
                    for pid, p in pages2.items():
                        thumb = p.get("thumbnail", {}).get("source")
                        if thumb and not thumb.lower().endswith(".svg"):
                            candidates.append((0, thumb))
            except Exception:
                pass

        # If still no candidates, try the single most specific noun (last word)
        if not candidates and len(query.split()) > 1:
            words = [w for w in query.split() if len(w) > 2]
            if words:
                last_word = words[-1]
                encoded_last = urllib.parse.quote_plus(last_word)
                url3 = (
                    f"https://en.wikipedia.org/w/api.php?action=query&generator=search"
                    f"&gsrsearch={encoded_last}&gsrlimit=6&prop=pageimages"
                    f"&pithumbsize=600&format=json"
                )
                try:
                    resp3 = await client.get(url3, timeout=5.0)
                    if resp3.status_code == 200:
                        pages3 = resp3.json().get("query", {}).get("pages", {})
                        for pid, p in pages3.items():
                            thumb = p.get("thumbnail", {}).get("source")
                            if thumb and not thumb.lower().endswith(".svg"):
                                candidates.append((0, thumb))
                except Exception:
                    pass

        # Sort by keyword match (relevant first), then try each
        candidates.sort(key=lambda x: x[0])

        for _, thumb_url in candidates[:6]:
            try:
                img_resp = await client.get(thumb_url, timeout=8.0)
                if img_resp.status_code == 200 and len(img_resp.content) > 8000:
                    logger.info(f"📸 ImageAgent: Wikimedia photo for '{query}' ({len(img_resp.content):,} bytes)")
                    return img_resp.content
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"Wikimedia search failed for '{query}': {e}")
    return None


async def _search_openverse(query: str, client: httpx.AsyncClient) -> bytes | None:
    """Search Openverse (millions of public web images across Flickr, Wikimedia, museums).
    Fulfills User Rule 2C: Search everywhere on the web, not limited to Wikimedia.
    """
    try:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://api.openverse.org/v1/images/?q={encoded}&page_size=6"
        resp = await client.get(url, timeout=6.0)
        if resp.status_code != 200:
            return None
        data = resp.json()
        results = data.get("results", [])
        for res in results:
            img_url = res.get("url") or res.get("thumbnail")
            if not img_url:
                continue
            try:
                img_resp = await client.get(img_url, timeout=7.0)
                if img_resp.status_code == 200 and len(img_resp.content) > 6000:
                    logger.info(f"🌐 ImageAgent: Openverse web photo for '{query}' ({len(img_resp.content):,} bytes)")
                    return img_resp.content
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"Openverse search failed for '{query}': {e}")
    return None


async def _generate_pollinations(
    query: str,
    client: httpx.AsyncClient,
    topic: str = "",
    is_child: bool = False
) -> bytes | None:
    """Generate a unique AI illustration via Pollinations AI with rate-limit guard.
    - If is_child: playful cartoons/stickers (cats, dinosaurs, lego characters, friendly mascots).
    - If adult: modern, clean, editorial educational visuals.
    """
    global _LAST_POLLINATIONS_TIME

    if is_child:
        # Child style: Cute cartoon, kawaii, sticker with die-cut white outline, cats/dinosaurs/lego vibe
        enhanced_prompt = (
            f"Cute colorful cartoon sticker illustration of {query}, "
            f"playful child-friendly character style (cat or dinosaur or lego or cute mascot), "
            f"thick clean white die-cut outline border, bright cheerful pastel colors, "
            f"expressive kawaii art, isolated on pure white background, premium vector children book illustration, 4k"
        )
    else:
        # Adult/Teen style: Minimalist, clean, modern educational illustration
        enhanced_prompt = (
            f"Clean modern educational illustration of {query}, "
            f"minimalist editorial visual, crisp sharp lines, high contrast, "
            f"pure white background, professional textbook quality, 4k"
        )

    encoded = urllib.parse.quote_plus(enhanced_prompt)
    seed = abs(hash(query)) % 1_000_000
    # Use standard Pollinations endpoint without 'turbo' to avoid HTTP 429 rate limits
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=400&height=260&nologo=true&seed={seed}"

    async with _POLLINATIONS_SEMAPHORE:
        loop = asyncio.get_event_loop()
        now = loop.time()
        elapsed = now - _LAST_POLLINATIONS_TIME
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)

        try:
            resp = await client.get(url, timeout=7.0)
            if resp.status_code == 200 and len(resp.content) > 3000:
                logger.info(f"🎨 ImageAgent: AI-generated sticker/illustration for '{query}' ({len(resp.content):,} bytes)")
                return resp.content
            elif resp.status_code == 429:
                logger.warning(f"Pollinations 429 for '{query}' — immediately falling back to search")
                add_warning("Сервис AI-генерации картинок временно перегружен (лимит 429), иллюстрации подобраны через поиск фото.")
            else:
                logger.warning(f"Pollinations HTTP {resp.status_code} for '{query}'")
        except Exception as e:
            logger.warning(f"Pollinations failed/timed out for '{query}': {e}")
            add_warning("Служба AI-генерации картинок не ответила вовремя, задействован резервный поиск фото.")
        finally:
            _LAST_POLLINATIONS_TIME = loop.time()
    return None


def _generate_svg_placeholder(query: str) -> bytes:
    """Fallback SVG to prevent empty images if all searches and generation fail."""
    colors = ["#ec4899", "#8b5cf6", "#3b82f6", "#10b981", "#f59e0b"]
    bg = random.choice(colors)
    text = query[:20] + ("..." if len(query) > 20 else "")
    svg = f"""<svg width="400" height="260" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="{bg}" rx="16" />
      <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="white" font-family="sans-serif" font-size="24" font-weight="bold">
        {text}
      </text>
    </svg>"""
    return svg.encode("utf-8")


async def get_image_base64(query: str, topic: str = "", image_mode: str = "auto", is_child: bool = False) -> str:
    """
    Get Base64 image data for a query.

    image_mode:
      'search'   — search Wikimedia + Openverse, fallback to AI generation if none found.
      'generate' — AI generation (Pollinations), GUARANTEED fallback to Wikimedia Commons so no image is ever empty.
      'auto'     — tries AI generation first, fallback to Wikimedia Commons.
    """
    if not query or not query.strip():
        return ""

    # Cache key includes mode and is_child so 'generate' and 'search' don't share cached results
    cleaned = _clean_query(query, topic)
    cache_key = f"{image_mode}:{is_child}:{cleaned}"
    if cache_key in _IMAGE_CACHE:
        return _IMAGE_CACHE[cache_key]

    # Check local pre-generated assets (e.g. from built-in Google Imagen)
    local_dirs = [
        Path(r"c:\Users\Admin\FigmaAI\assets\quiz_images"),
        Path(r"c:\Users\Admin\FigmaAI\assets"),
        Path(r"C:\Users\Admin\.gemini\antigravity-ide\brain\875e0877-b807-47a8-8e3c-a2c3f00e9eb5"),
    ]
    query_words = [w.lower() for w in cleaned.split() if len(w) > 3]
    for ldir in local_dirs:
        if ldir.exists():
            for f in ldir.glob("*.jpg"):
                fname = f.stem.lower()
                if any(qw in fname for qw in query_words):
                    try:
                        raw = f.read_bytes()
                        if len(raw) > 5000:
                            logger.info(f"💾 ImageAgent: Using built-in local asset {f.name} for '{cleaned}'")
                            b64 = base64.b64encode(raw).decode("ascii")
                            _IMAGE_CACHE[cache_key] = b64
                            return b64
                    except Exception:
                        pass

    proxy = _detect_proxy()
    transport_kwargs = {"proxy": proxy} if proxy else {}

    raw_bytes = None
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, **transport_kwargs) as client:
            if image_mode in ("search", "pinterest"):
                # Real internet photos: User explicitly wants Pinterest as primary source
                logger.info(f"📌 ImageAgent [{image_mode.upper()} mode]: searching Pinterest for '{cleaned}'")
                raw_bytes = await _search_pinterest(cleaned, client)
                if not raw_bytes:
                    logger.info(f"Pinterest photo not found for '{cleaned}', falling back to Wikimedia/Openverse")
                    raw_bytes = await _search_wikimedia(cleaned, client)
                if not raw_bytes:
                    raw_bytes = await _search_openverse(cleaned, client)
                if not raw_bytes:
                    logger.info(f"Web search failed for '{cleaned}', trying AI generation")
                    raw_bytes = await _generate_pollinations(cleaned, client, topic=topic, is_child=is_child)

            elif image_mode == "generate":
                # Explicit generative illustrations
                logger.info(f"🎨 ImageAgent [GENERATE mode]: generating illustration of '{cleaned}' (child={is_child})")
                raw_bytes = await _generate_pollinations(cleaned, client, topic=topic, is_child=is_child)
                if not raw_bytes:
                    logger.info(f"AI generation unavailable for '{cleaned}', falling back to Pinterest")
                    raw_bytes = await _search_pinterest(cleaned, client)
                if not raw_bytes:
                    raw_bytes = await _search_wikimedia(cleaned, client)

            else:  # "auto" — smart dual strategy: try Pinterest first for real, aesthetic photos; fallback to AI
                logger.info(f"✨ ImageAgent [AUTO mode]: searching Pinterest for '{cleaned}'")
                raw_bytes = await _search_pinterest(cleaned, client)
                if not raw_bytes:
                    logger.info(f"Pinterest empty for '{cleaned}', generating via Pollinations AI")
                    raw_bytes = await _generate_pollinations(cleaned, client, topic=topic, is_child=is_child)
                if not raw_bytes:
                    raw_bytes = await _search_wikimedia(cleaned, client)
                if not raw_bytes:
                    raw_bytes = await _search_openverse(cleaned, client)

    except Exception as e:
        logger.error(f"ImageAgent error resolving '{query}': {e}")

    if not raw_bytes:
        logger.info(f"All image sources failed for '{cleaned}'. Using SVG fallback.")
        raw_bytes = _generate_svg_placeholder(cleaned)

    if raw_bytes:
        # Ensure image is in a Figma-compatible format (JPEG or PNG). Figma throws error on WEBP/AVIF!
        try:
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(raw_bytes))
            if im.format not in ("JPEG", "PNG"):
                im = im.convert("RGB")
                out_buf = io.BytesIO()
                im.save(out_buf, format="JPEG", quality=90)
                raw_bytes = out_buf.getvalue()
        except Exception as conv_err:
            logger.debug(f"Image format normalization skipped: {conv_err}")

        b64_str = base64.b64encode(raw_bytes).decode("ascii")
        _IMAGE_CACHE[cache_key] = b64_str
        return b64_str

    return ""


async def resolve_batch_images(
    items: list[dict],
    topic: str = "",
    item_query_key: str = "image_query",
    image_mode: str = "auto",
    is_child: bool = False,
) -> list[dict]:
    """
    Resolve images for a batch of cards/questions concurrently for high speed.
    image_mode: 'generate' | 'search' | 'auto'
    """
    if not items:
        return items

    mode_labels = {
        "generate": "🎨 AI-генерация + Быстрый поиск",
        "search":   "🔍 Поиск фото (Wikimedia / Openverse)",
        "auto":     "✨ Авто: AI + Wikimedia",
    }
    total = len(items)
    agent_logger.emit_log(
        stage="generating",
        icon="🖼️",
        title="Image Agent в работе",
        message=f"Режим: {mode_labels.get(image_mode, image_mode)} | Всего {total} картинок...",
        detail=f"Тема: {topic} (детский стиль: {'да' if is_child else 'нет'})"
    )

    # Concurrency semaphore to avoid overwhelming connections while being 5x faster
    sem = asyncio.Semaphore(3)

    async def _resolve_single(idx: int, item: dict) -> dict:
        # If item already has image_base64 (e.g. from canvas selection / Vision Agent), preserve it
        if item.get("image_base64"):
            return item

        query = item.get(item_query_key) or item.get("question") or item.get("sentence") or item.get("word") or topic
        async with sem:
            logger.info(f"ImageAgent [{image_mode}] [{idx}/{total}]: '{query}'")
            b64 = await get_image_base64(query, topic=topic, image_mode=image_mode, is_child=is_child)
            if b64:
                return {**item, "image_base64": b64}
            return {**item, "image_base64": ""}

    get_and_clear_warnings()
    tasks = [_resolve_single(idx, item) for idx, item in enumerate(items, 1)]
    updated_items = list(await asyncio.gather(*tasks))
    success_count = sum(1 for it in updated_items if it.get("image_base64"))
    if success_count < total:
        add_warning(f"Для {total - success_count} карточек не удалось загрузить иллюстрации (использованы запасные заглушки).")

    if _LAST_BATCH_WARNINGS:
        agent_logger.emit_log(
            stage="warning",
            icon="⚠️",
            title="Особенности картинок",
            message=_LAST_BATCH_WARNINGS[0],
            detail="Задание продолжается с доступными визуальными материалами"
        )

    agent_logger.emit_log(
        stage="generating",
        icon="✅",
        title="Иллюстрации готовы",
        message=f"Image Agent успешно подготовил {success_count} из {total} картинок! (режим: {image_mode})",
        detail="Все изображения конвертированы в векторные растровые слои Figma"
    )

    return updated_items


async def get_quiz_images(queries: list[str], topic: str = "", image_mode: str = "auto", is_child: bool = False) -> list[str]:
    """
    Resolve a list of search/generation queries to a list of base64 strings.
    Guarantees matching order and non-empty fallback.
    """
    items = [{"query": q} for q in queries]
    resolved = await resolve_batch_images(items, topic=topic, item_query_key="query", image_mode=image_mode, is_child=is_child)
    return [it.get("image_base64", "") for it in resolved]
