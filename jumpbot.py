"""Window-scoped capture and cautious experiment runner for 跳一跳.

No jump is sent unless both the pawn and the target top are visible.
"""
from __future__ import annotations

import argparse
import ctypes
# Match physical pixels used by Pillow capture and mouse coordinates on a
# display with Windows scaling (the test machine uses 150%).
ctypes.windll.user32.SetProcessDPIAware()
import json
import time
from pathlib import Path

import numpy as np
import cv2
from PIL import Image
from model import JumpModel
import win32api
import win32con
import win32gui
import win32ui

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
STOP = ROOT / "STOP"
PAUSE = ROOT / "PAUSE"
MODEL = JumpModel(DATA / "model.json")
CENTER_TEMPLATES = DATA / "center_templates.npz"
_center_template_cache = (None, None)


def trained_center(image_array, approximate, current):
    """Use only a strong match to a human-labeled platform exemplar."""
    global _center_template_cache
    if approximate is None or current is None or not CENTER_TEMPLATES.exists():
        return None
    modified = CENTER_TEMPLATES.stat().st_mtime_ns
    if _center_template_cache[0] != modified:
        with np.load(CENTER_TEMPLATES) as file:
            _center_template_cache = (modified,
                                      (file["patches"].copy(), file["widths"].copy()))
    patches, widths = _center_template_cache[1]
    gray = cv2.cvtColor(image_array.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    best = (0.985, None)
    for patch, trained_width in zip(patches, widths):
        if trained_width != gray.shape[1]:
            continue
        ph, pw = patch.shape
        x0 = max(0, round(approximate[0]-75-pw/2))
        y0 = max(0, round(approximate[1]-55-ph/2))
        x1 = min(gray.shape[1], round(approximate[0]+75+pw/2))
        y1 = min(gray.shape[0], round(approximate[1]+55+ph/2))
        roi = gray[y0:y1, x0:x1]
        if roi.shape[0] < ph or roi.shape[1] < pw:
            continue
        score_map = cv2.matchTemplate(roi, patch, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(score_map)
        center = [float(x0+location[0]+pw/2), float(y0+location[1]+ph/2)]
        if (score > best[0] and np.hypot(center[0]-approximate[0],
                                        center[1]-approximate[1]) < 15 and
                center[1] < current[1]-25):
            best = (score, center)
    return best[1]


def window():
    h = win32gui.FindWindow(None, "跳一跳")
    if not h or not win32gui.IsWindowVisible(h):
        raise RuntimeError("找不到可见的“跳一跳”窗口")
    return h


def capture(h):
    left, top, right, bottom = win32gui.GetWindowRect(h)
    width, height = right - left, bottom - top
    dc = win32gui.GetWindowDC(h)
    src = win32ui.CreateDCFromHandle(dc)
    mem = src.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(src, width, height)
    mem.SelectObject(bitmap)
    try:
        if not ctypes.windll.user32.PrintWindow(h, mem.GetSafeHdc(), 2):
            raise RuntimeError("PrintWindow 失败")
        image = Image.frombuffer("RGB", (width, height), bitmap.GetBitmapBits(True), "raw", "BGRX", 0, 1).copy()
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        mem.DeleteDC()
        src.DeleteDC()
        win32gui.ReleaseDC(h, dc)
    if np.asarray(image).mean() < 8:
        raise RuntimeError("窗口截图几乎全黑，停止操作")
    return image


def observe(image, debug=False, current_hint=None):
    """Conservative color segmentation; missing/uncertain targets are explicit."""
    a = np.asarray(image).astype(np.int16)
    height, width = a.shape[:2]
    game_over_variant = None
    if width >= 500 and height >= 900:
        record_panel = a[int(height*.24):int(height*.50),
                         int(width*.13):int(width*.85)]
        if np.mean(np.max(record_panel, axis=2) < 110) > .7:
            game_over_variant = "record"
        # A single dark block edge and a pale background used to look exactly
        # like the end-screen panel and replay button. Require broad regions.
        for variant, panel_y, button_y in (("record", .22, .83),
                                            ("normal", .48, .75)):
            panel = a[int(height*(panel_y-.025)):int(height*(panel_y+.025)),
                      int(width*.10):int(width*.22)]
            button = a[int(height*(button_y-.018)):int(height*(button_y+.018)),
                       int(width*.67):int(width*.84)]
            if (game_over_variant is None and
                    np.mean(np.max(panel, axis=2) < 110) > .7 and
                    np.mean(np.min(button, axis=2) > 210) > .6):
                game_over_variant = variant
                break
    if game_over_variant:
        return {"pawn_contact": None, "target_top_center": None,
                "target_geometric_center": None, "current_top_center": None,
                "title_visible": False, "game_over": True,
                "game_over_variant": game_over_variant, "ready": False,
                "image_size": [width, height]}
    # The animated title screen includes moving platforms and a pawn. Its
    # large white logo must never be mistaken for active gameplay.
    if height > 900:
        title_roi = a[int(height*.20):int(height*.34), int(width*.22):int(width*.82)]
    else:
        title_roi = a[int(height*.32):int(height*.48), int(width*.32):]
    title_visible = bool(len(title_roi) and np.sum(np.all(title_roi > 242, axis=2)) > 1800)
    # Dark purple pawn body, below the game header.
    dark = ((a[:, :, 2] > a[:, :, 1] + 18) & (a[:, :, 0] < 115) &
            (a[:, :, 1] < 105) & (a[:, :, 2] < 125))
    dark[:max(65, height // 5)] = False
    ys, xs = np.where(dark)
    pawn = None
    if len(xs) > 120:
        bins, edges = np.histogram(xs, bins=max(1, width // 8), range=(0, width))
        x0 = int(edges[np.argmax(bins)])
        choose = (xs >= x0 - 16) & (xs <= x0 + 24)
        if choose.sum() > 80:
            pawn = [float(np.median(xs[choose])), float(np.percentile(ys[choose], 98))]
            if (pawn[0] < 30 or pawn[0] > width - 30 or
                    pawn[1] < height * .55 or pawn[1] > height - 30):
                pawn = None
    # The rendered top faces have broad flat color regions. Separate them by
    # exact RGB color before connected components so touching platforms with
    # different shaded sides cannot merge into a false center.
    region = a[max(65, height // 3):]
    pixels = region.reshape(-1, 3).astype(np.uint32)
    packed = (pixels[:, 0] << 16) | (pixels[:, 1] << 8) | pixels[:, 2]
    values, frequencies = np.unique(packed, return_counts=True)
    colors = np.stack(((values >> 16) & 255, (values >> 8) & 255,
                       values & 255), axis=1).astype(np.int16)
    popular = [i for i in np.argsort(frequencies)[::-1]
               if frequencies[i] >= 350 and int(colors[i].max())-int(colors[i].min()) < 9]
    candidates = []
    small_candidates = []
    for color_index in popular:
        color = colors[color_index]
        mask = np.all(a == color, axis=2).astype(np.uint8)
        mask[:max(65, height // 3)] = 0
        count, labels, stats, centers = cv2.connectedComponentsWithStats(mask, 8)
        for i in range(1, count):
            sx, sy, sw, sh, area = map(int, stats[i])
            if (area < 350 or sw < 30 or sh < 20 or sw / sh > 4 or
                    sx < 8 or sx + sw > width - 8 or sy + sh > height - 8 or
                    sw > width * .7 or sh > height * .3):
                continue
            candidate = [float(sx + (sw - 1) / 2), float(centers[i, 1]), area, sx, sx+sw]
            (candidates if area >= 1000 and sw >= 65 and sh >= 35
             else small_candidates).append(candidate)
    hsv = cv2.cvtColor(a.astype(np.uint8), cv2.COLOR_RGB2HSV)
    for hue_lo, hue_hi in [(0, 8), (8, 18), (18, 30), (30, 42),
                            (42, 55), (55, 75), (75, 100), (100, 130), (130, 180)]:
        # Pale pink patterned tops have S around 40. The blue sky still
        # needs a higher floor, while yellow backgrounds remain excluded.
        saturation_floor = (70 if 100 <= hue_lo < 130 else 80 if 18 <= hue_lo < 30
                            else 35 if hue_lo >= 130 else 33)
        saturated = ((hsv[:, :, 0] >= hue_lo) & (hsv[:, :, 0] < hue_hi) &
                     (hsv[:, :, 1] > saturation_floor) & (hsv[:, :, 2] > 125) &
                     (hsv[:, :, 2] < 250)).astype(np.uint8)
        saturated[:max(65, height // 3)] = 0
        saturated = cv2.morphologyEx(saturated, cv2.MORPH_CLOSE,
                                     np.ones((7, 7), dtype=np.uint8))
        count, _, stats, centers = cv2.connectedComponentsWithStats(saturated, 8)
        for i in range(1, count):
            sx, sy, sw, sh, area = map(int, stats[i])
            if (area < 500 or sw < 30 or sh < 20 or
                    sx < 8 or sx + sw > width - 8 or sy + sh > height - 8 or
                    sw > width * .7 or sh > height * .3):
                continue
            # A narrow blue bottle exposes only its side in the blue mask;
            # its pale cap is about half a body width above that component.
            top_y = (sy - sw * .5 if 100 <= hue_lo < 130 and sw < 90 and sh < 80
                     else sy + min(sw / 4, sh * .45))
            candidate = [float(sx + (sw-1)/2), float(top_y), area, sx, sx+sw]
            (candidates if area >= 2500 and sw >= 70 and sh >= 50
             else small_candidates).append(candidate)
    primary_candidates = candidates.copy()
    candidates.extend(small_candidates)
    # Dark textured brown blocks were invisible to the bright-color masks.
    brown = ((hsv[:, :, 0] < 22) & (hsv[:, :, 1] > 30) &
             (hsv[:, :, 2] > 55) & (hsv[:, :, 2] < 165)).astype(np.uint8)
    brown[:max(65, height // 3)] = 0
    brown = cv2.morphologyEx(brown, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(brown, 8)
    brown_candidates = []
    for i in range(1, count):
        sx, sy, sw, sh, area = map(int, stats[i])
        if (area < 500 or sw < 35 or sh < 25 or sx < 8 or
                sx + sw > width - 8 or sy + sh > height - 8 or
                sw > width * .7 or sh > height * .3):
            continue
        brown_candidate = [float(sx + (sw-1)/2), float(sy + min(sw/4, sh*.45)),
                           area, sx, sx+sw]
        brown_candidates.append(brown_candidate)
        candidates.append(brown_candidate)
    # White rings on small cylindrical platforms consist of several shades;
    # grouping near-white pixels yields the top even when no one shade is large.
    pale = ((hsv[:, :, 1] < 12) & (hsv[:, :, 2] > 215)).astype(np.uint8)
    pale[:max(65, height // 3)] = 0
    pale = cv2.morphologyEx(pale, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    count, _, stats, centers = cv2.connectedComponentsWithStats(pale, 8)
    for i in range(1, count):
        sx, sy, sw, sh, area = map(int, stats[i])
        if (area < 500 or sw < 35 or sh < 25 or sx < 8 or
                sx + sw > width - 8 or sy + sh > height - 8 or
                sw > width * .7 or sh > height * .3):
            continue
        candidates.append([float(sx + (sw-1)/2), float(centers[i, 1]),
                           area, sx, sx+sw])
    # Gray miniature cylinders have dark top rings and medium-gray sides.
    # Group adjacent shades while excluding the more saturated background.
    neutral_mid = ((hsv[:, :, 1] < 12) & (hsv[:, :, 2] >= 90) &
                   (hsv[:, :, 2] <= 205)).astype(np.uint8)
    neutral_mid[:max(65, height // 3)] = 0
    neutral_mid = cv2.morphologyEx(neutral_mid, cv2.MORPH_CLOSE,
                                   np.ones((7, 7), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(neutral_mid, 8)
    for i in range(1, count):
        sx, sy, sw, sh, area = map(int, stats[i])
        if (area < 500 or sw < 30 or sh < 20 or sx < 8 or
                sx + sw > width - 8 or sy + sh > height - 8 or
                sw > width * .7 or sh > height * .3):
            continue
        candidates.append([float(sx + (sw-1)/2), float(sy + min(sw/4, sh*.45)),
                           area, sx, sx+sw])
    # Find compact white landing markers before assigning the supporting
    # platform. Close, similarly colored blocks can merge and be discarded as
    # one oversized component, while a target marker remains visible.
    surface_markers = []
    if pawn:
        bright = np.all(a > 235, axis=2).astype(np.uint8)
        n_markers, _, marker_stats, marker_centers = cv2.connectedComponentsWithStats(bright, 8)
        for marker_id in range(1, n_markers):
            mx, my, mw, mh, ma = map(int, marker_stats[marker_id])
            cx, cy = marker_centers[marker_id]
            if not (50 <= ma <= 700 and 6 <= mw <= 40 and 4 <= mh <= 30 and
                    abs(cx-pawn[0]) > 45 and cy < pawn[1]-40 and cy > height*.4):
                continue
            top = [c for c in candidates if c[2] >= 500 and
                   abs(cx-c[0]) < 35 and abs(cy-c[1]) < 22 and
                   c[1] < pawn[1]-35]
            if top:
                geometry = min(top, key=lambda c: abs(cx-c[0])+abs(cy-c[1]))[:2]
                surface_markers.append(([float(cx), float(cy)], geometry))
    current = None
    target = None
    target_geometry = None
    current_source = None
    if pawn and candidates:
        possible_current = [c for c in candidates if abs(c[0]-pawn[0]) < 80 and
                            c[3]-10 <= pawn[0] <= c[4]+10 and
                            pawn[1]-115 < c[1] < pawn[1]+45]
        # On the narrow white pedestal its cap is hidden by the pawn and its
        # gray stem is too thin for the usual platform component thresholds.
        # Confirm the stem directly beneath the feet before using the pawn
        # contact as the supporting platform position.
        if not possible_current:
            px, py = int(pawn[0]), int(pawn[1])
            stem = a[py+5:min(height, py+85), max(0, px-17):min(width, px+18)]
            if stem.size:
                gray = ((stem.max(axis=2)-stem.min(axis=2) < 18) &
                        (stem.mean(axis=2) >= 105) & (stem.mean(axis=2) <= 205))
                if np.count_nonzero(gray) > 350:
                    possible_current = [[pawn[0], pawn[1], int(np.count_nonzero(gray)),
                                         px-17, px+18]]
        if not possible_current and current_hint is not None:
            hx, hy = current_hint
            if np.hypot(hx-pawn[0], hy-pawn[1]) < 45:
                possible_current = [[float(hx), float(hy), 0,
                                     float(hx)-20, float(hx)+20]]
        if not possible_current and len(surface_markers) == 1:
            possible_current = [[pawn[0], pawn[1], 0,
                                 pawn[0]-20, pawn[0]+20]]
            current_source = "pawn_contact_marker_supported"
        if possible_current:
            current = min(possible_current,
                          key=lambda c: np.hypot(c[0]-pawn[0], c[1]-pawn[1]))[:2]
            possible_targets = [c for c in primary_candidates if c[1] < current[1]-30 and
                                abs(c[0]-current[0]) > 100 and c[2] >= 1000]
            if not possible_targets:
                possible_targets = [c for c in candidates if c[1] < current[1]-30 and
                                    abs(c[0]-current[0]) > 100 and c[2] >= 500]
            if possible_targets:
                chosen = max(possible_targets, key=lambda c: c[2])
                upper = [c for c in candidates if
                         20 < chosen[1]-c[1] < 100 and
                         abs(chosen[0]-c[0]) < 65 and
                         max(0, min(chosen[4], c[4])-max(chosen[3], c[3])) /
                         max(1, min(chosen[4]-chosen[3], c[4]-c[3])) > .7 and
                         c[2] >= chosen[2]*.5]
                if upper:
                    chosen = min(upper, key=lambda c: c[1])
                target = chosen[:2]
                target_geometry = target.copy()
                bright = np.all(a > 235, axis=2).astype(np.uint8)
                n_markers, _, marker_stats, marker_centers = cv2.connectedComponentsWithStats(bright, 8)
                markers = []
                for marker_id in range(1, n_markers):
                    mx, my, mw, mh, ma = map(int, marker_stats[marker_id])
                    cx, cy = marker_centers[marker_id]
                    if (50 <= ma <= 700 and 6 <= mw <= 40 and 4 <= mh <= 30 and
                            abs(cx-target[0]) < 35 and abs(cy-target[1]) < 22 and
                            cy < current[1]-45):
                        markers.append((abs(cx-target[0])+abs(cy-target[1]), [float(cx), float(cy)]))
                if markers:
                    target = min(markers, key=lambda item: item[0])[1]
                    matching_brown = [c for c in brown_candidates if
                                      np.hypot(c[0]-target[0], c[1]-target[1]) < 40]
                    if matching_brown:
                        target_geometry = min(matching_brown,
                                              key=lambda c: np.hypot(c[0]-target[0], c[1]-target[1]))[:2]
            else:
                # Touching platforms of the same color can merge into one
                # component. A small white surface marker still identifies
                # the next landing point, without claiming a measured center.
                bright = np.all(a > 235, axis=2).astype(np.uint8)
                n_markers, _, marker_stats, marker_centers = cv2.connectedComponentsWithStats(bright, 8)
                markers = []
                for marker_id in range(1, n_markers):
                    mx, my, mw, mh, ma = map(int, marker_stats[marker_id])
                    cx, cy = marker_centers[marker_id]
                    if (50 <= ma <= 700 and 6 <= mw <= 40 and 4 <= mh <= 30 and
                            abs(cx-pawn[0]) > 45 and cy < pawn[1]-40 and
                            cy > height*.4):
                        markers.append((abs(cy-current[1]), [float(cx), float(cy)]))
                if markers:
                    target = min(markers, key=lambda item: item[0])[1]
                    matching_top = [c for c in candidates if c[2] >= 500 and
                                    np.hypot(c[0]-target[0], c[1]-target[1]) < 15 and
                                    c[1] < current[1]-30]
                    if matching_top:
                        target_geometry = min(matching_top,
                                              key=lambda c: np.hypot(c[0]-target[0], c[1]-target[1]))[:2]
                else:
                    near = [c for c in primary_candidates if
                            c[1] < current[1]-45 and 45 < abs(c[0]-current[0]) <= 100 and
                            c[2] >= 800]
                    if not near:
                        near = [c for c in candidates if
                                c[1] < current[1]-45 and 45 < abs(c[0]-current[0]) <= 100 and
                                c[2] >= 500]
                    if near:
                        target = max(near, key=lambda c: c[2])[:2]
                        target_geometry = target.copy()
            if len(surface_markers) == 1:
                marker, geometry = surface_markers[0]
                if (target is None or np.hypot(target[0]-geometry[0],
                                              target[1]-geometry[1]) < 70):
                    target, target_geometry = marker, geometry
    trained = trained_center(a, target_geometry or target, current)
    if trained is not None:
        target = trained
    result = {"pawn_contact": pawn, "target_top_center": target,
            "target_geometric_center": target_geometry,
            "current_top_center": current,
            "title_visible": title_visible, "game_over": False,
            "game_over_variant": None,
            "ready": bool(pawn and target and not title_visible), "image_size": [width, height]}
    if trained is not None:
        result["target_center_source"] = "human_labeled_template"
    elif target is not None and len(surface_markers) == 1 and target == surface_markers[0][0]:
        result["target_center_source"] = "white_surface_marker"
    if current_source:
        result["current_center_source"] = current_source
    if debug:
        result["candidates"] = candidates
    return result


def recover_occluded_platform(before, after, initial, final):
    """Project the old target through camera motion when the pawn hides it.

    This only aids locating the next target. A projected center is not a
    measured landing point and must never enter jump-distance training.
    """
    if final["ready"] or final["game_over"] or not final["pawn_contact"]:
        return final
    anchor = initial.get("target_geometric_center") or initial.get("target_top_center")
    if anchor is None or before.size != after.size or score_change(before, after)[0] < 80:
        return final
    pre = cv2.Canny(np.asarray(before.convert("L")), 40, 100).astype(np.float32)
    post = cv2.Canny(np.asarray(after.convert("L")), 40, 100).astype(np.float32)
    pre[:int(before.height*.26)] = 0
    post[:int(after.height*.26)] = 0
    (dx, dy), response = cv2.phaseCorrelate(pre, post)
    projected = [anchor[0] + dx, anchor[1] + dy]
    foot = final["pawn_contact"]
    if (response < .25 or abs(projected[0]-foot[0]) > 35 or
            abs(projected[1]-foot[1]) > 40):
        return final
    recovered = observe(after, current_hint=projected)
    if recovered["ready"]:
        recovered["current_center_source"] = "tracked_from_previous_frame"
        recovered["camera_shift"] = [dx, dy]
        recovered["camera_shift_response"] = response
        return recovered
    return final


def start_game(h, image):
    state = observe(image)
    if not state["title_visible"] or state["game_over"]:
        raise RuntimeError("未确认开始界面，拒绝点击")
    if STOP.exists() or PAUSE.exists() or win32gui.GetForegroundWindow() != h:
        raise RuntimeError("开始游戏时控制权限不满足")
    left, top, right, bottom = win32gui.GetWindowRect(h)
    if (right-left, bottom-top) != image.size:
        raise RuntimeError("截图后窗口大小变化")
    x, y = left + int(image.width*.5), top + int(image.height*.69)
    if win32gui.WindowFromPoint((x, y)) not in (h, *children(h)):
        raise RuntimeError("开始按钮被其他窗口遮挡")
    win32api.SetCursorPos((x, y))
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(.08)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(2)


def measure_landing(before: Image.Image, after: Image.Image, initial: dict, final: dict):
    """Track the old target across camera motion and measure contact error.

    Returns no distance when template matching or pawn localization is uncertain.
    """
    if (not initial["ready"] or initial.get("target_geometric_center") is None or
            final["pawn_contact"] is None or final["current_top_center"] is None):
        return None
    if before.size != after.size:
        return None
    changed_score_pixels, score_change_fraction = score_change(before, after)
    if changed_score_pixels < 80:
        return None
    # The pre-jump target becomes the supporting platform after a successful
    # landing. This cancels a pure camera translation without image matching.
    matched = np.array(final["current_top_center"], dtype=float)
    pawn_after = np.array(final["pawn_contact"], dtype=float)
    if np.linalg.norm(pawn_after - matched) > 75:
        return None
    pawn_before = np.array(initial["pawn_contact"], dtype=float)
    target_before = np.array(initial.get("target_geometric_center") or initial["target_top_center"], dtype=float)
    vector = target_before - pawn_before
    norm = float(np.linalg.norm(vector))
    if norm < 20:
        return None
    unit = vector / norm
    error = float(np.dot(pawn_after - matched, unit))
    transverse = float(unit[0] * (pawn_after[1] - matched[1]) - unit[1] * (pawn_after[0] - matched[0]))
    # A pawn more than 25 pixels from the supposed center is usually a
    # neighboring face selected as the platform; keep the successful jump
    # but do not train on its unreliable distance.
    if abs(error) > 25 or abs(transverse) > 70:
        return None
    return {"distance": norm + error, "target_distance": norm,
            "landing_error": error, "transverse_error": transverse,
            "measurement_confidence": .7, "direction": 1 if vector[0] >= 0 else -1,
            "success_estimate": True, "score_change_fraction": score_change_fraction}


def score_change(before: Image.Image, after: Image.Image):
    if before.size != after.size:
        return 0, 0.0
    pre = np.asarray(before)
    post = np.asarray(after)
    scale_x, scale_y = before.width / 632, before.height / 1160
    x0, x1 = int(65*scale_x), int(280*scale_x)
    y0, y1 = int(170*scale_y), int(245*scale_y)
    score_before = np.any(pre[y0:y1, x0:x1] < 110, axis=2)
    score_after = np.any(post[y0:y1, x0:x1] < 110, axis=2)
    changed = score_before ^ score_after
    return int(np.count_nonzero(changed)), float(np.mean(changed))


def append(record):
    with (DATA / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def press(h, seconds):
    if STOP.exists():
        raise RuntimeError("STOP 文件存在")
    if win32gui.GetForegroundWindow() != h:
        raise RuntimeError("游戏窗口不是前台窗口，拒绝发送输入")
    # Cursor and input are constrained to the current game client rectangle.
    left, top, right, bottom = win32gui.GetWindowRect(h)
    x, y = (left + right) // 2, (top + bottom) // 2
    if win32gui.WindowFromPoint((x, y)) not in (h, *children(h)):
        raise RuntimeError("按压位置被其他窗口遮挡")
    win32api.SetCursorPos((x, y))
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    start = time.perf_counter()
    try:
        while time.perf_counter() - start < seconds:
            if STOP.exists() or PAUSE.exists() or (win32api.GetAsyncKeyState(win32con.VK_F12) & 0x8000):
                STOP.touch()
                raise RuntimeError("紧急停止")
            if win32gui.GetForegroundWindow() != h:
                raise RuntimeError("按压期间游戏窗口失去焦点")
            if win32gui.GetWindowRect(h) != (left, top, right, bottom):
                raise RuntimeError("按压期间游戏窗口位置变化")
            time.sleep(.01)
    finally:
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    return time.perf_counter() - start


def children(h):
    found = []
    win32gui.EnumChildWindows(h, lambda c, _: found.append(c), None)
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "capture", "observe", "stop", "pause", "resume", "trial", "auto", "until-fail", "model"])
    parser.add_argument("--seconds", type=float)
    parser.add_argument("--max-jumps", type=int, default=100)
    args = parser.parse_args()
    if args.command == "stop":
        STOP.touch()
        print("已停止后续操作")
        return
    if args.command == "resume":
        STOP.unlink(missing_ok=True)
        PAUSE.unlink(missing_ok=True)
        print("已恢复操作许可")
        return
    if args.command == "pause":
        PAUSE.touch()
        print("已暂停后续操作")
        return
    if args.command == "model":
        print(json.dumps({"samples": len(MODEL.samples), "fit": MODEL.fit()}, ensure_ascii=False, indent=2))
        return
    if args.command == "auto":
        auto(args.max_jumps)
        return
    if args.command == "until-fail":
        until_fail(args.max_jumps)
        return
    h = window()
    image = capture(h)
    stamp = time.strftime("%Y%m%d_%H%M%S") + f"_{time.time_ns()%1_000_000_000:09d}"
    path = DATA / f"capture_{stamp}.png"
    image.save(path)
    obs = observe(image)
    result = {"time": stamp, "window_rect": win32gui.GetWindowRect(h),
              "foreground": win32gui.GetForegroundWindow() == h,
              "capture": str(path), **obs}
    if args.command == "status":
        result["paused"] = PAUSE.exists()
        result["stopped"] = STOP.exists()
        result["model_sample_count"] = len(MODEL.samples)
        if obs["ready"]:
            pawn = np.array(obs["pawn_contact"])
            target = np.array(obs["target_top_center"])
            distance = float(np.linalg.norm(target-pawn))
            result["target_distance_pixels"] = distance
            result["prediction"] = MODEL.press_for(distance, image.width,
                                                    1 if target[0] > pawn[0] else -1)
        events_path = DATA / "events.jsonl"
        if events_path.exists():
            rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
            trials = [row for row in rows if "actual_press_seconds" in row]
            result["real_press_trials"] = len(trials)
            result["measured_successes"] = sum(bool(row.get("measurement", {}).get("success_estimate"))
                                               for row in trials if row.get("measurement"))
    if args.command == "trial":
        if not obs["ready"]:
            raise RuntimeError("棋子或完整目标平台未可靠识别，拒绝跳跃")
        if args.seconds is None or not 0.05 <= args.seconds <= 2.0:
            raise ValueError("trial 需要 --seconds，范围 0.05 至 2 秒")
        if PAUSE.exists():
            raise RuntimeError("PAUSE 文件存在")
        result["requested_press_seconds"] = args.seconds
        result["actual_press_seconds"] = press(h, args.seconds)
        time.sleep(2)
        after = capture(h)
        after_path = DATA / f"after_{stamp}.png"
        after.save(after_path)
        result["after_capture"] = str(after_path)
        result["after_observation"] = observe(after)
        measurement = measure_landing(image, after, obs, result["after_observation"])
        result["measurement"] = measurement
        result["valid_measurement"] = measurement is not None
        if measurement is not None:
            MODEL.add(seconds=result["actual_press_seconds"],
                      distance=measurement["distance"], direction=measurement["direction"],
                      screen_width=image.width, confidence=measurement["measurement_confidence"], source="real")
    append(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def auto(max_jumps: int):
    # CLI launches often leave the shell in front. Activate the discovered
    # game once; if focus later changes, the safety checks stop input.
    if not STOP.exists() and not PAUSE.exists():
        game = window()
        if win32gui.GetForegroundWindow() != game:
            try:
                win32gui.SetForegroundWindow(game)
            except Exception:
                pass
            time.sleep(.3)
            if win32gui.GetForegroundWindow() != game:
                ctypes.windll.user32.SwitchToThisWindow(game, True)
                time.sleep(.5)
            if win32gui.GetForegroundWindow() != game:
                raise RuntimeError("无法将游戏窗口置于前台")
    if max_jumps < 1:
        raise ValueError("max-jumps 必须大于零")
    attempts = 0
    idle = 0
    while attempts < max_jumps and not STOP.exists():
        if win32api.GetAsyncKeyState(win32con.VK_F12) & 0x8000:
            STOP.touch()
            print("F12 紧急停止")
            return
        if PAUSE.exists():
            time.sleep(.5)
            continue
        try:
            h = window()
            before = capture(h)
            obs = observe(before)
            if obs["title_visible"]:
                start_game(h, before)
                idle = 0
                continue
            if obs["game_over"]:
                game_over_path = DATA / f"game_over_{time.time_ns()}.png"
                before.save(game_over_path)
                append({"time": time.strftime("%Y%m%d_%H%M%S"), "state": "game_over",
                        "capture": str(game_over_path), "score": None})
                print("已检测到失败，保存结算截图并停止；未重开")
                return
            if win32gui.GetForegroundWindow() != h or not obs["ready"]:
                idle += 1
                if idle >= 30:
                    print("连续 30 次无法安全识别或窗口不在前台；自动停止")
                    return
                time.sleep(1)
                continue
            idle = 0
            pawn = np.array(obs["pawn_contact"])
            target = np.array(obs["target_top_center"])
            distance = float(np.linalg.norm(target-pawn))
            direction = 1 if target[0] > pawn[0] else -1
            prediction = MODEL.press_for(distance, before.width, direction)
            if prediction is None:
                if MODEL.fit() is not None:
                    print("目标距离超出已校准范围，安全停止")
                    return
                # Distinct exploratory durations are explicitly experiments,
                # not a claimed calibrated jump model.
                sequence = [.20, .32, .44, .56, .68, .80, .92, 1.04]
                seconds = sequence[len(MODEL.samples) % len(sequence)]
            else:
                if prediction["uncertainty_pixels"] > 25:
                    print("模型不确定性过高，停止自动跳跃")
                    return
                seconds = prediction["seconds"]
            stamp = time.strftime("%Y%m%d_%H%M%S") + f"_{time.time_ns()%1_000_000_000:09d}"
            before_path = DATA / f"before_{stamp}.png"
            before.save(before_path)
            actual_seconds = press(h, seconds)
            time.sleep(2)
            after = capture(h)
            after_path = DATA / f"after_{stamp}.png"
            after.save(after_path)
            final = observe(after)
            final = recover_occluded_platform(before, after, obs, final)
            measurement = measure_landing(before, after, obs, final)
            if final.get("current_center_source"):
                measurement = None
            event = {"time": stamp, "before_capture": str(before_path),
                     "after_capture": str(after_path), "before": obs, "after": final,
                     "requested_press_seconds": seconds,
                     "actual_press_seconds": actual_seconds, "prediction": prediction,
                     "measurement": measurement, "valid_measurement": measurement is not None}
            append(event)
            if measurement is None:
                changed_pixels, changed_fraction = score_change(before, after)
                if changed_pixels >= 80 and final["ready"]:
                    append({"time": stamp, "state": "success_unmeasured",
                            "reason": "平台中心不可靠", "score_change_fraction": changed_fraction})
                    attempts += 1
                    continue
                terminal = None
                for _ in range(10):
                    time.sleep(1)
                    candidate = capture(h)
                    if observe(candidate)["game_over"]:
                        terminal = candidate
                        break
                if terminal is not None:
                    game_over_path = DATA / f"game_over_{time.time_ns()}.png"
                    terminal.save(game_over_path)
                    append({"time": time.strftime("%Y%m%d_%H%M%S"), "state": "game_over",
                            "capture": str(game_over_path), "score": None,
                            "preceding_jump": stamp})
                    attempts += 1
                    print("已检测到失败，保存结算截图并停止；未重开")
                    return
                print("落点无法可靠测量；停止自动跳跃")
                return
            MODEL.add(seconds=actual_seconds, distance=measurement["distance"],
                      direction=direction, screen_width=before.width,
                      confidence=measurement["measurement_confidence"], source="real")
            attempts += 1
            print(json.dumps({"attempt": attempts, "measurement": measurement}, ensure_ascii=False), flush=True)
        except Exception as exc:
            append({"time": time.strftime("%Y%m%d_%H%M%S"), "error": str(exc)})
            print(f"安全停止：{exc}")
            return


def until_fail(max_jumps: int):
    """Run one game, preserving every frame pair; never start or restart."""
    if max_jumps < 1:
        raise ValueError("max-jumps 必须大于零")
    if STOP.exists() or PAUSE.exists():
        raise RuntimeError("STOP 或 PAUSE 文件存在")
    h = window()
    if win32gui.GetForegroundWindow() != h:
        win32gui.SetForegroundWindow(h)
        time.sleep(.4)
    if win32gui.GetForegroundWindow() != h:
        raise RuntimeError("游戏窗口不是前台窗口")
    session = DATA / "review" / time.strftime("%Y%m%d_%H%M%S")
    session.mkdir(parents=True, exist_ok=False)
    manifest = session / "jumps.jsonl"

    def log(row):
        with manifest.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"复盘目录：{session.resolve()}", flush=True)
    for number in range(1, max_jumps + 1):
        if STOP.exists() or PAUSE.exists() or (win32api.GetAsyncKeyState(win32con.VK_F12) & 0x8000):
            log({"state": "stopped", "before_jump": number})
            return
        try:
            before = capture(h)
            initial = observe(before)
            if initial["game_over"]:
                before.save(session / "failure.png")
                log({"state": "game_over", "before_jump": number, "capture": "failure.png"})
                print("已检测到失败，未重开", flush=True)
                return
            if not initial["ready"]:
                before.save(session / "uncertain.png")
                log({"state": "uncertain", "before_jump": number, "capture": "uncertain.png"})
                print("无法可靠识别，安全停止", flush=True)
                return
            pawn = np.array(initial["pawn_contact"])
            target = np.array(initial["target_top_center"])
            distance = float(np.linalg.norm(target - pawn))
            direction = 1 if target[0] > pawn[0] else -1
            prediction = MODEL.press_for(distance, before.width, direction)
            if prediction is None or prediction["uncertainty_pixels"] > 25:
                before.save(session / "uncertain.png")
                log({"state": "model_uncertain", "before_jump": number,
                     "capture": "uncertain.png", "prediction": prediction})
                print("模型预测不可靠，安全停止", flush=True)
                return
            prefix = f"jump_{number:04d}"
            before_name = prefix + "_before.png"
            after_name = prefix + "_after.png"
            before.save(session / before_name)
            actual = press(h, prediction["seconds"])
            time.sleep(2)
            after = capture(h)
            after.save(session / after_name)
            final = observe(after)
            final = recover_occluded_platform(before, after, initial, final)
            measurement = measure_landing(before, after, initial, final)
            if final.get("current_center_source"):
                measurement = None
            changed, _ = score_change(before, after)
            row = {"jump": number, "before": before_name, "after": after_name,
                   "initial": initial, "final": final, "prediction": prediction,
                   "actual_press_seconds": actual, "measurement": measurement,
                   "score_changed_pixels": changed}
            if measurement is not None:
                row["outcome"] = "success_measured"
                MODEL.add(seconds=actual, distance=measurement["distance"],
                          direction=direction, screen_width=before.width,
                          confidence=measurement["measurement_confidence"], source="real")
                log(row)
                print(f"第 {number} 跳成功，落点误差 {measurement['landing_error']:.1f} px", flush=True)
                continue
            if changed >= 80 and final["ready"]:
                row["outcome"] = "success_unmeasured"
                log(row)
                print(f"第 {number} 跳成功，落点未可靠测量", flush=True)
                continue
            for _ in range(10):
                if final["game_over"]:
                    break
                time.sleep(1)
                after = capture(h)
                final = observe(after)
            if final["game_over"]:
                after.save(session / "failure.png")
                row["outcome"] = "failure"
                row["failure_capture"] = "failure.png"
                log(row)
                print(f"第 {number} 跳失败，已保存截图，未重开", flush=True)
                return
            row["outcome"] = "uncertain_stopped"
            after.save(session / "uncertain.png")
            log(row)
            print("跳跃结果不确定，安全停止", flush=True)
            return
        except Exception as exc:
            log({"state": "error", "jump": number, "error": str(exc)})
            print(f"安全停止：{exc}", flush=True)
            return
    log({"state": "jump_limit", "max_jumps": max_jumps})


if __name__ == "__main__":
    main()
