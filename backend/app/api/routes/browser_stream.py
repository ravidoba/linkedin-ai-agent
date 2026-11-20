"""Authenticated, read-only preview of the current Playwright browser."""

import base64

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse

from app.core.dependencies import get_current_user
from app.models.user import User
from app.services import apply_workflow

router = APIRouter(prefix="/browser", tags=["Browser"])


@router.get("/frame")
async def current_browser_frame(
    current_user: User = Depends(get_current_user),
):
    """Return one JPEG frame; never start a browser or navigate a page."""
    context = apply_workflow._context
    owner_id = apply_workflow._browser_owner_id

    if context is None or owner_id is None:
        return JSONResponse({"status": "disconnected"}, headers={"Cache-Control": "no-store"})
    if owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Browser session is not yours")

    try:
        pages = [p for p in context.pages if not p.is_closed()]
        if not pages:
            return JSONResponse({"status": "loading"}, headers={"Cache-Control": "no-store"})
        page = pages[-1]
        jpeg = await page.screenshot(type="jpeg", quality=55, timeout=5000, animations="disabled")
        viewport = page.viewport_size or {"width": 1280, "height": 720}
        return JSONResponse(
            {
                "status": "connected",
                "manual_control": apply_workflow._manual_owner_id == current_user.id,
                "url": page.url,
                "frame": {
                    "src": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii"),
                    "width": viewport["width"],
                    "height": viewport["height"],
                },
            },
            headers={"Cache-Control": "no-store"},
        )
    except Exception:
        # Navigation and page closure can interrupt a screenshot; retry next poll.
        return JSONResponse({"status": "loading"}, headers={"Cache-Control": "no-store"})


@router.get("/activity")
async def browser_activity(after: int = 0, current_user: User = Depends(get_current_user)):
    events = [e for e in apply_workflow._activity.get(current_user.id, ()) if e["id"] > after]
    return {"events": events, "last_id": apply_workflow._activity_sequence.get(current_user.id, 0)}


class BrowserAction(BaseModel):
    action: str
    x: float | None = Field(default=None, ge=0)
    y: float | None = Field(default=None, ge=0)
    delta_y: float | None = Field(default=None, ge=-5000, le=5000)
    text: str | None = Field(default=None, max_length=500)
    key: str | None = Field(default=None, max_length=50)


def _owned_page(user: User):
    if apply_workflow._browser_owner_id != user.id:
        raise HTTPException(403, "Browser session is not yours")
    ctx = apply_workflow._context
    if ctx is None:
        raise HTTPException(409, "No active browser")
    pages = [p for p in ctx.pages if not p.is_closed()]
    if not pages:
        raise HTTPException(409, "No open page")
    return pages[-1]


@router.post("/takeover")
async def take_over(current_user: User = Depends(get_current_user)):
    _owned_page(current_user)
    if apply_workflow._lock.locked():
        raise HTTPException(409, "Agent is running. Wait for it to finish before taking control")
    if apply_workflow._manual_owner_id not in (None, current_user.id):
        raise HTTPException(409, "Another user controls the browser")
    apply_workflow._manual_owner_id = current_user.id
    return {"manual_control": True}


@router.post("/release")
async def release_control(current_user: User = Depends(get_current_user)):
    _owned_page(current_user)
    if apply_workflow._manual_owner_id != current_user.id:
        raise HTTPException(409, "You do not have manual control")
    apply_workflow._manual_owner_id = None
    return {"manual_control": False}


@router.post("/action")
async def browser_action(action: BrowserAction, current_user: User = Depends(get_current_user)):
    page = _owned_page(current_user)
    if apply_workflow._manual_owner_id != current_user.id or apply_workflow._lock.locked():
        raise HTTPException(409, "Take control after the agent stops")
    if action.action == "click":
        if action.x is None or action.y is None:
            raise HTTPException(422, "Coordinates required")
        await page.mouse.click(action.x, action.y)
    elif action.action == "scroll":
        await page.mouse.wheel(0, action.delta_y or 0)
    elif action.action == "type":
        if not action.text:
            raise HTTPException(422, "Text required")
        await page.keyboard.insert_text(action.text)
    elif action.action == "key":
        allowed = {"Enter", "Tab", "Escape", "Backspace", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"}
        if action.key not in allowed:
            raise HTTPException(422, "Unsupported key")
        await page.keyboard.press(action.key)
    else:
        raise HTTPException(422, "Unsupported action")
    return {"ok": True}
