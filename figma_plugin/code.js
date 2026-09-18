// Antigravity Live Bridge — Figma / FigJam Plugin
if (typeof __html__ !== 'undefined') {
  figma.showUI(__html__, { width: 320, height: 195, title: "ESL Remote" });
}

function getTOCStatus() {
  try {
    const tocs = figma.currentPage.children.filter(n =>
      (n.getPluginData && (n.getPluginData("role") === "table_of_contents" || n.getPluginData("is_toc") === "true")) ||
      (n.name && (n.name.includes("ОГЛАВЛЕНИЕ") || n.name.includes("Table of Contents")))
    );
    if (tocs.length === 0) {
      return { exists: false, isVisible: false };
    }
    const isVisible = tocs.some(n => n.visible);
    return { exists: true, isVisible: isVisible };
  } catch (e) {
    return { exists: false, isVisible: false };
  }
}

// Send current document metadata to UI
function sendDocInfo() {
  const tocStat = getTOCStatus();
  figma.ui.postMessage({
    type: "DOC_INFO",
    title: figma.root.name || "Untitled",
    isFigJam: typeof figma.createShapeWithText === "function"
  });
  figma.ui.postMessage({
    type: "TOC_STATUS",
    exists: tocStat.exists,
    isVisible: tocStat.isVisible
  });
}

// Center camera viewport smoothly on the Table of Contents block
async function navigateToTableOfContents() {
  try {
    let tocs = figma.currentPage.children.filter(n =>
      (n.getPluginData && (n.getPluginData("role") === "table_of_contents" || n.getPluginData("is_toc") === "true")) ||
      (n.name && (n.name.includes("ОГЛАВЛЕНИЕ") || n.name.includes("Table of Contents")))
    );

    // If not found on current page, check other pages in the document
    if (tocs.length === 0 && figma.root && figma.root.children) {
      for (const page of figma.root.children) {
        if (page === figma.currentPage) continue;
        const pageTocs = page.children.filter(n =>
          (n.getPluginData && (n.getPluginData("role") === "table_of_contents" || n.getPluginData("is_toc") === "true")) ||
          (n.name && (n.name.includes("ОГЛАВЛЕНИЕ") || n.name.includes("Table of Contents")))
        );
        if (pageTocs.length > 0) {
          figma.currentPage = page;
          tocs = pageTocs;
          break;
        }
      }
    }

    // If still not found on canvas, automatically build the TOC from existing blocks!
    if (tocs.length === 0) {
      figma.notify("📑 Оглавление не найдено. Создаю оглавление...", { timeout: 2000 });
      await refreshTableOfContents();
      tocs = figma.currentPage.children.filter(n =>
        (n.getPluginData && (n.getPluginData("role") === "table_of_contents" || n.getPluginData("is_toc") === "true")) ||
        (n.name && (n.name.includes("ОГЛАВЛЕНИЕ") || n.name.includes("Table of Contents")))
      );
    }

    if (tocs.length > 0) {
      const target = tocs[0];
      // If TOC was hidden, make it visible
      if (!target.visible) {
        target.visible = true;
        figma.ui.postMessage({ type: "TOC_STATUS", exists: true, isVisible: true });
      }
      figma.viewport.scrollAndZoomIntoView([target]);
      try {
        figma.currentPage.selection = [target];
      } catch (e) { }
      figma.notify("🎯 Камера сфокусирована на оглавлении!", { timeout: 2000 });
      return { success: true, targetId: target.id };
    } else {
      figma.notify("⚠️ Не удалось найти или создать оглавление", { timeout: 2500 });
      return { success: false, error: "TOC node could not be created or found" };
    }
  } catch (err) {
    figma.notify("✕ Ошибка перехода к оглавлению: " + String(err), { timeout: 3000 });
    return { success: false, error: String(err) };
  }
}
// ── Board Backup & Restore Engine ──────────────────────────────────────────
function findBoardBackupGroup() {
  try {
    return figma.currentPage.children.find(n =>
      (n.getPluginData && n.getPluginData("role") === "board_backup") ||
      (n.name && (n.name.startsWith("🔒 [РЕЗЕРВНАЯ КОПИЯ ДОСКИ]") || n.name.startsWith("🔒 [БЭКАП ДОСКИ]")))
    );
  } catch (e) {
    return null;
  }
}

function sendSelectionInfo() {
  try {
    const existingBackup = findBoardBackupGroup();
    const rawSel = figma.currentPage.selection || [];
    const sel = rawSel.filter(n =>
      n !== existingBackup &&
      !(n.getPluginData && n.getPluginData("role") === "board_backup") &&
      !(n.name && (n.name.startsWith("🔒 [РЕЗЕРВНАЯ КОПИЯ ДОСКИ]") || n.name.startsWith("🔒 [БЭКАП ДОСКИ]")))
    );
    figma.ui.postMessage({
      type: "SELECTION_CHANGE",
      count: sel.length
    });
  } catch (e) {
    console.warn("sendSelectionInfo error:", e);
  }
}

sendDocInfo();
sendSelectionInfo();

figma.clientStorage.getAsync("bridge_url").then((savedUrl) => {
  if (savedUrl) {
    figma.ui.postMessage({
      type: "SETTINGS_LOADED",
      bridgeUrl: savedUrl
    });
  }
}).catch(() => {});

figma.on("documentchange", () => {
  sendDocInfo();
  sendBackupStatus();
  sendSelectionInfo();
});

function sendBackupStatus() {
  try {
    const backupGroup = findBoardBackupGroup();
    if (backupGroup) {
      const time = (backupGroup.getPluginData && backupGroup.getPluginData("backup_time")) || "Ранее";
      const countStr = (backupGroup.getPluginData && backupGroup.getPluginData("backup_count")) || "";
      const count = countStr ? parseInt(countStr, 10) : (backupGroup.children ? backupGroup.children.length : 0);
      figma.ui.postMessage({
        type: "BACKUP_STATUS",
        hasBackup: true,
        time: time,
        count: count
      });
    } else {
      figma.ui.postMessage({
        type: "BACKUP_STATUS",
        hasBackup: false
      });
    }
  } catch (e) {
    console.warn("sendBackupStatus error:", e);
  }
}
sendBackupStatus();

async function createBoardBackup() {
  try {
    const existingBackup = findBoardBackupGroup();
    const targetNodes = figma.currentPage.children.filter(n =>
      n !== existingBackup &&
      !(n.getPluginData && n.getPluginData("role") === "board_backup") &&
      !(n.name && (n.name.startsWith("🔒 [РЕЗЕРВНАЯ КОПИЯ ДОСКИ]") || n.name.startsWith("🔒 [БЭКАП ДОСКИ]")))
    );

    if (!targetNodes || targetNodes.length === 0) {
      figma.notify("⚠️ Доска пуста, нечего сохранять", { timeout: 2500 });
      sendBackupStatus();
      return { success: false, reason: "empty" };
    }

    const clones = [];
    for (const node of targetNodes) {
      try {
        const origX = typeof node.x === "number" ? node.x : 0;
        const origY = typeof node.y === "number" ? node.y : 0;
        const clone = node.clone();
        if (clone.setPluginData) {
          clone.setPluginData("orig_x", String(origX));
          clone.setPluginData("orig_y", String(origY));
        }
        clones.push(clone);
      } catch (err) {
        console.warn("Failed to clone node:", node.name, err);
      }
    }

    if (clones.length === 0) {
      figma.notify("❌ Не удалось скопировать элементы", { timeout: 2500 });
      sendBackupStatus();
      return { success: false, reason: "clone_failed" };
    }

    if (existingBackup) {
      try { existingBackup.remove(); } catch (e) {}
    }

    const backupGroup = figma.group(clones, figma.currentPage);
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    const months = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
    const dateStr = `${now.getDate()} ${months[now.getMonth()]} ${hh}:${mm}`;

    backupGroup.name = `🔒 [РЕЗЕРВНАЯ КОПИЯ ДОСКИ] ${dateStr} (${clones.length} эл.)`;
    if (backupGroup.setPluginData) {
      backupGroup.setPluginData("role", "board_backup");
      backupGroup.setPluginData("backup_time", dateStr);
      backupGroup.setPluginData("backup_count", String(clones.length));
    }
    backupGroup.visible = false;
    backupGroup.locked = true;
    backupGroup.x = -999999;
    backupGroup.y = -999999;

    try {
      await figma.clientStorage.setAsync("board_backup_meta", JSON.stringify({
        time: dateStr,
        count: clones.length,
        timestamp: Date.now()
      }));
    } catch (e) {}

    figma.notify(`📦 Резервная копия создана: ${clones.length} эл. (${dateStr})`, { timeout: 3000 });

    figma.ui.postMessage({
      type: "BACKUP_STATUS",
      hasBackup: true,
      time: dateStr,
      count: clones.length
    });

    return { success: true, count: clones.length, time: dateStr };
  } catch (err) {
    console.error("createBoardBackup error:", err);
    figma.notify("❌ Ошибка бэкапа: " + err.message, { timeout: 3000 });
    sendBackupStatus();
    return { success: false, error: String(err) };
  }
}

async function restoreBoardBackup() {
  try {
    const backupGroup = findBoardBackupGroup();
    if (!backupGroup || !backupGroup.children || backupGroup.children.length === 0) {
      figma.notify("⚠️ Резервная копия не найдена на этой доске", { timeout: 3000 });
      figma.ui.postMessage({ type: "BACKUP_RESTORED", success: false });
      sendBackupStatus();
      return { success: false, reason: "not_found" };
    }

    const backupChildren = Array.from(backupGroup.children);
    const dateStr = (backupGroup.getPluginData && backupGroup.getPluginData("backup_time")) || "";

    // 1. Удаляем все текущие элементы на холсте, кроме группы бэкапа
    const currentNodes = figma.currentPage.children.filter(n => n !== backupGroup);
    for (const n of currentNodes) {
      try { n.remove(); } catch (e) {}
    }

    // 2. Клонируем элементы из бэкапа обратно на холст
    const restoredNodes = [];
    for (const child of backupChildren) {
      try {
        const restored = child.clone();
        figma.currentPage.appendChild(restored);
        restored.visible = true;
        restored.locked = child.locked;

        const origX = child.getPluginData ? parseFloat(child.getPluginData("orig_x")) : NaN;
        const origY = child.getPluginData ? parseFloat(child.getPluginData("orig_y")) : NaN;
        if (!isNaN(origX) && !isNaN(origY)) {
          restored.x = origX;
          restored.y = origY;
        }
        restoredNodes.push(restored);
      } catch (err) {
        console.warn("Failed to restore node from backup:", child.name, err);
      }
    }

    if (restoredNodes.length > 0) {
      try {
        figma.currentPage.selection = restoredNodes;
        figma.viewport.scrollAndZoomIntoView(restoredNodes);
      } catch (e) {}

      figma.notify(`🔄 Доска восстановлена: ${restoredNodes.length} эл.! (${dateStr})`, { timeout: 3500 });

      figma.ui.postMessage({
        type: "BACKUP_RESTORED",
        success: true,
        count: restoredNodes.length
      });

      const tocStat = getTOCStatus();
      figma.ui.postMessage({
        type: "TOC_STATUS",
        exists: tocStat.exists,
        isVisible: tocStat.isVisible
      });

      sendBackupStatus();
      return { success: true, count: restoredNodes.length };
    } else {
      figma.notify("⚠️ Не удалось восстановить элементы", { timeout: 3000 });
      figma.ui.postMessage({ type: "BACKUP_RESTORED", success: false });
      sendBackupStatus();
      return { success: false, reason: "restore_empty" };
    }
  } catch (err) {
    console.error("restoreBoardBackup error:", err);
    figma.notify("❌ Ошибка восстановления: " + err.message, { timeout: 3000 });
    figma.ui.postMessage({ type: "BACKUP_RESTORED", success: false });
    sendBackupStatus();
    return { success: false, error: String(err) };
  }
}

// ── JSON File Serialization / Deserialization Engine ───────────────────────
function uint8ToBase64(bytes) {
  if (typeof figma.base64Encode === "function") {
    try { return figma.base64Encode(bytes); } catch (_) {}
  }
  let binary = "";
  const len = bytes.byteLength;
  const chunkSize = 8192;
  for (let i = 0; i < len; i += chunkSize) {
    const chunk = bytes.subarray(i, Math.min(i + chunkSize, len));
    binary += String.fromCharCode.apply(null, chunk);
  }
  return (typeof btoa === 'function') ? btoa(binary) : "";
}

async function serializeNode(node, mediaCollector = null) {
  if (!node) return null;
  const data = {
    type: node.type,
    name: node.name || "",
    x: typeof node.x === "number" ? node.x : 0,
    y: typeof node.y === "number" ? node.y : 0,
    width: typeof node.width === "number" ? node.width : 100,
    height: typeof node.height === "number" ? node.height : 100,
    visible: node.visible !== false,
    locked: !!node.locked,
  };

  if (typeof node.rotation === "number" && node.rotation !== 0) {
    data.rotation = node.rotation;
  }

  // Plugin Data (roles, blockId, tags, toc)
  if (typeof node.getPluginDataKeys === "function") {
    try {
      const keys = node.getPluginDataKeys();
      if (keys && keys.length > 0) {
        data.pluginData = {};
        for (const k of keys) {
          data.pluginData[k] = node.getPluginData(k);
        }
      }
    } catch (_) {}
  } else if (typeof node.getPluginData === "function") {
    try {
      const role = node.getPluginData("role");
      if (role) {
        data.pluginData = { role: role };
        const bId = node.getPluginData("blockId");
        if (bId) data.pluginData.blockId = bId;
      }
    } catch (_) {}
  }

  // Fills & Images
  if (node.fills && Array.isArray(node.fills)) {
    data.fills = [];
    for (const f of node.fills) {
      if (f.type === "IMAGE" && f.imageHash) {
        try {
          const img = figma.getImageByHash(f.imageHash);
          if (img) {
            let bytes = await img.getBytesAsync();
            // Защита от переполнения памяти: если растр > 1.5 МБ, сжимаем до 1600px JPEG
            if (bytes && bytes.byteLength > 1.5 * 1024 * 1024 && typeof node.exportAsync === "function") {
              try {
                const optBytes = await node.exportAsync({
                  format: "JPG",
                  constraint: { type: "WIDTH", value: 1600 }
                });
                if (optBytes && optBytes.byteLength > 0 && optBytes.byteLength < bytes.byteLength) {
                  bytes = optBytes;
                }
              } catch (_) {}
            }
            const b64 = uint8ToBase64(bytes);
            if (mediaCollector && mediaCollector.files) {
              const idx = mediaCollector.files.length + 1;
              const isJpg = (bytes && bytes.length > 2 && bytes[0] === 0xFF && bytes[1] === 0xD8);
              const ext = isJpg ? "jpg" : "png";
              const mediaPath = `media/image_${String(idx).padStart(3, "0")}.${ext}`;
              mediaCollector.files.push({
                path: mediaPath,
                name: `image_${String(idx).padStart(3, "0")}.${ext}`,
                bytesBase64: b64
              });
              data.fills.push({
                type: "IMAGE",
                scaleMode: f.scaleMode || "FILL",
                mediaRef: mediaPath
              });
              continue;
            } else {
              data.fills.push({
                type: "IMAGE",
                scaleMode: f.scaleMode || "FILL",
                imageBytesBase64: b64
              });
              continue;
            }
          }
        } catch (imgErr) {
          console.warn("Could not export image bytes for fill:", imgErr);
        }
      }
      data.fills.push(f);
    }
  }

  // Strokes
  if (node.strokes && Array.isArray(node.strokes)) {
    data.strokes = node.strokes;
  }
  if (typeof node.strokeWeight === "number") data.strokeWeight = node.strokeWeight;
  if (node.strokeAlign) data.strokeAlign = node.strokeAlign;

  // Corner radius
  if (typeof node.cornerRadius === "number") data.cornerRadius = node.cornerRadius;

  // Opacity & effects
  if (typeof node.opacity === "number" && node.opacity !== 1) data.opacity = node.opacity;
  if (node.effects && Array.isArray(node.effects) && node.effects.length > 0) {
    data.effects = node.effects;
  }

  // Text specific
  if (node.type === "TEXT") {
    data.characters = node.characters || "";
    data.fontSize = typeof node.fontSize === "number" ? node.fontSize : 16;
    if (node.fontName && typeof node.fontName === "object") {
      data.fontName = {
        family: node.fontName.family || "Inter",
        style: node.fontName.style || "Regular"
      };
    }
    data.textAlignHorizontal = node.textAlignHorizontal || "LEFT";
    data.textAlignVertical = node.textAlignVertical || "TOP";
  }

  // FigJam specific & Vectors
  if (node.type === "SHAPE_WITH_TEXT") {
    if (node.shapeType) data.shapeType = node.shapeType;
    if (node.text && node.text.characters) {
      data.characters = node.text.characters;
    }
  }
  if (node.type === "STICKY") {
    if (node.text && node.text.characters) {
      data.characters = node.text.characters;
    }
  }
  if (node.type === "CONNECTOR") {
    if (node.connectorLineType) data.connectorLineType = node.connectorLineType;
    if (node.text && node.text.characters) data.characters = node.text.characters;
  }
  if (node.type === "VECTOR" && node.vectorPaths) {
    data.vectorPaths = node.vectorPaths;
  }
  if (node.type === "CODE_BLOCK") {
    if (node.code) data.code = node.code;
    if (node.codeLanguage) data.codeLanguage = node.codeLanguage;
  }

  // Children (рекурсивно)
  if (node.children && Array.isArray(node.children) && node.children.length > 0) {
    data.children = [];
    for (const child of node.children) {
      const childData = await serializeNode(child, mediaCollector);
      if (childData) data.children.push(childData);
    }
  }

  return data;
}

async function deserializeNode(data, parentNode, mediaMap = null) {
  if (!data) return null;
  const parent = parentNode || figma.currentPage;
  let node = null;

  try {
    if (data.type === "FRAME") {
      node = figma.createFrame();
      parent.appendChild(node);
    } else if (data.type === "RECTANGLE") {
      node = figma.createRectangle();
      parent.appendChild(node);
    } else if (data.type === "ELLIPSE") {
      node = figma.createEllipse();
      parent.appendChild(node);
    } else if (data.type === "POLYGON") {
      node = figma.createPolygon();
      parent.appendChild(node);
    } else if (data.type === "STAR") {
      node = figma.createStar();
      parent.appendChild(node);
    } else if (data.type === "LINE") {
      node = figma.createLine();
      parent.appendChild(node);
    } else if (data.type === "SECTION" && typeof figma.createSection === "function") {
      node = figma.createSection();
      parent.appendChild(node);
    } else if (data.type === "STICKY" && typeof figma.createSticky === "function") {
      node = figma.createSticky();
      parent.appendChild(node);
      if (data.characters && node.text) {
        try {
          await figma.loadFontAsync({ family: "Inter", style: "Medium" });
          node.text.characters = data.characters;
        } catch (_) {}
      }
    } else if (data.type === "SHAPE_WITH_TEXT" && typeof figma.createShapeWithText === "function") {
      node = figma.createShapeWithText();
      parent.appendChild(node);
      if (data.shapeType) {
        try { node.shapeType = data.shapeType; } catch (_) {}
      }
      if (data.characters && node.text) {
        try {
          await figma.loadFontAsync({ family: "Inter", style: "Regular" });
          node.text.characters = data.characters;
        } catch (_) {}
      }
    } else if (data.type === "VECTOR") {
      node = figma.createVector();
      parent.appendChild(node);
      if (data.vectorPaths && Array.isArray(data.vectorPaths)) {
        try { node.vectorPaths = data.vectorPaths; } catch (_) {}
      }
    } else if (data.type === "CONNECTOR" && typeof figma.createConnector === "function") {
      node = figma.createConnector();
      parent.appendChild(node);
      if (data.connectorLineType) {
        try { node.connectorLineType = data.connectorLineType; } catch (_) {}
      }
      if (data.characters && node.text) {
        try {
          await figma.loadFontAsync({ family: "Inter", style: "Regular" });
          node.text.characters = data.characters;
        } catch (_) {}
      }
    } else if (data.type === "CODE_BLOCK" && typeof figma.createCodeBlock === "function") {
      node = figma.createCodeBlock();
      parent.appendChild(node);
      if (data.code) {
        try { node.code = data.code; } catch (_) {}
      }
      if (data.codeLanguage) {
        try { node.codeLanguage = data.codeLanguage; } catch (_) {}
      }
    } else if (data.type === "TEXT") {
      node = figma.createText();
      parent.appendChild(node);
      const fontFam = (data.fontName && data.fontName.family) || "Inter";
      const fontSty = (data.fontName && data.fontName.style) || "Regular";
      try {
        await figma.loadFontAsync({ family: fontFam, style: fontSty });
        node.fontName = { family: fontFam, style: fontSty };
      } catch (e) {
        try {
          await figma.loadFontAsync({ family: "Inter", style: "Regular" });
          node.fontName = { family: "Inter", style: "Regular" };
        } catch (_) {}
      }
      if (data.characters !== undefined) {
        node.characters = data.characters;
      }
      if (typeof data.fontSize === "number") node.fontSize = data.fontSize;
      if (data.textAlignHorizontal) node.textAlignHorizontal = data.textAlignHorizontal;
      if (data.textAlignVertical) node.textAlignVertical = data.textAlignVertical;
    } else if (data.type === "GROUP") {
      const childNodes = [];
      if (data.children && data.children.length > 0) {
        for (const childData of data.children) {
          const childNode = await deserializeNode(childData, parent, mediaMap);
          if (childNode) childNodes.push(childNode);
        }
      }
      if (childNodes.length > 0) {
        try {
          node = figma.group(childNodes, parent);
        } catch (e) {
          node = figma.createFrame();
          parent.appendChild(node);
          for (const cn of childNodes) node.appendChild(cn);
        }
      } else {
        node = figma.createFrame();
        parent.appendChild(node);
      }
    } else {
      node = figma.createFrame();
      parent.appendChild(node);
    }

    if (!node) return null;

    if (data.name) node.name = data.name;
    if (typeof data.x === "number") node.x = data.x;
    if (typeof data.y === "number") node.y = data.y;
    if (data.type !== "GROUP" && typeof data.width === "number" && typeof data.height === "number" && data.width > 0 && data.height > 0) {
      try {
        if (typeof node.resize === "function") node.resize(data.width, data.height);
      } catch (_) {}
    }
    if (typeof data.rotation === "number" && data.rotation !== 0) {
      try { node.rotation = data.rotation; } catch (_) {}
    }

    // Fills (with Images & mediaRef resolution)
    if (data.fills && Array.isArray(data.fills) && node.fills !== undefined) {
      try {
        const restoredFills = [];
        for (const f of data.fills) {
          if (f.type === "IMAGE") {
            let b64 = f.imageBytesBase64;
            if (!b64 && f.mediaRef && mediaMap) {
              b64 = mediaMap[f.mediaRef] || mediaMap[f.mediaRef.replace("media/", "")];
            }
            if (b64) {
              try {
                let bytes;
                if (typeof figma.base64Decode === "function") {
                  bytes = figma.base64Decode(b64);
                } else {
                  const bin = atob(b64);
                  bytes = new Uint8Array(bin.length);
                  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                }
                const newImg = figma.createImage(bytes);
                restoredFills.push({
                  type: "IMAGE",
                  scaleMode: f.scaleMode || "FILL",
                  imageHash: newImg.hash
                });
                continue;
              } catch (imgErr) {
                console.warn("Failed to recreate image fill:", imgErr);
              }
            }
          }
          restoredFills.push(f);
        }
        node.fills = restoredFills;
      } catch (fErr) {
        console.warn("Could not set fills on node:", fErr);
      }
    }

    // Strokes
    if (data.strokes && Array.isArray(data.strokes) && node.strokes !== undefined) {
      try { node.strokes = data.strokes; } catch (_) {}
    }
    if (data.strokeWeight !== undefined && node.strokeWeight !== undefined) {
      try { node.strokeWeight = data.strokeWeight; } catch (_) {}
    }
    if (data.strokeAlign && node.strokeAlign !== undefined) {
      try { node.strokeAlign = data.strokeAlign; } catch (_) {}
    }

    // Corner radius
    if (typeof data.cornerRadius === "number" && node.cornerRadius !== undefined) {
      try { node.cornerRadius = data.cornerRadius; } catch (_) {}
    }

    // Opacity
    if (typeof data.opacity === "number" && node.opacity !== undefined) {
      try { node.opacity = data.opacity; } catch (_) {}
    }

    // Plugin Data
    if (data.pluginData && typeof node.setPluginData === "function") {
      for (const [k, v] of Object.entries(data.pluginData)) {
        try { node.setPluginData(k, String(v)); } catch (_) {}
      }
    }

    // Children (for frames / sections)
    if (data.type !== "GROUP" && data.children && Array.isArray(data.children) && data.children.length > 0) {
      for (const childData of data.children) {
        await deserializeNode(childData, node, mediaMap);
      }
    }

    if (data.visible !== undefined) {
      try { node.visible = data.visible; } catch (_) {}
    }
    if (data.locked !== undefined) {
      try { node.locked = data.locked; } catch (_) {}
    }

    return node;
  } catch (err) {
    console.error("deserializeNode error:", err);
    return node;
  }
}

async function exportBoardToFile(options = {}) {
  try {
    const isSelection = options && options.scope === "selection";
    const existingBackup = findBoardBackupGroup();
    let targetNodes = [];

    if (isSelection) {
      const sel = figma.currentPage.selection || [];
      targetNodes = sel.filter(n =>
        n !== existingBackup &&
        !(n.getPluginData && n.getPluginData("role") === "board_backup") &&
        !(n.name && (n.name.startsWith("🔒 [РЕЗЕРВНАЯ КОПИЯ ДОСКИ]") || n.name.startsWith("🔒 [БЭКАП ДОСКИ]")))
      );
      if (!targetNodes || targetNodes.length === 0) {
        figma.notify("⚠️ Сначала выделите элементы на холсте для бэкапа", { timeout: 2500 });
        figma.ui.postMessage({ type: "BACKUP_ERROR", message: "no_selection" });
        return { success: false, reason: "no_selection" };
      }
    } else {
      // 1. Также создаем скрытый клон для быстрого восстановления
      await createBoardBackup();

      targetNodes = figma.currentPage.children.filter(n =>
        n !== existingBackup &&
        !(n.getPluginData && n.getPluginData("role") === "board_backup") &&
        !(n.name && (n.name.startsWith("🔒 [РЕЗЕРВНАЯ КОПИЯ ДОСКИ]") || n.name.startsWith("🔒 [БЭКАП ДОСКИ]")))
      );

      if (!targetNodes || targetNodes.length === 0) {
        figma.notify("⚠️ Доска пуста, нечего сохранять в файл", { timeout: 2500 });
        figma.ui.postMessage({ type: "BACKUP_ERROR", message: "empty" });
        return { success: false, reason: "empty" };
      }
    }

    const isSplit = options && options.format === "split";
    const isZip = !!(options && options.isZip);

    const startMsg = isSelection
      ? (isSplit ? "📦 Формирование архива выделенных элементов..." : "📦 Сохранение выделенных элементов...")
      : (isSplit ? "📦 Формирование раздельного пакета бэкапа..." : "📦 Формирование файла бэкапа доски...");
    figma.notify(startMsg, { timeout: 2000 });

    const mediaCollector = isSplit ? { files: [] } : null;
    const serializedNodes = [];
    for (const n of targetNodes) {
      const s = await serializeNode(n, mediaCollector);
      if (s) serializedNodes.push(s);
    }

    const now = new Date();
    const pad = (num) => String(num).padStart(2, "0");
    const yyyy = now.getFullYear();
    const mm = pad(now.getMonth() + 1);
    const dd = pad(now.getDate());
    const hh = pad(now.getHours());
    const min = pad(now.getMinutes());
    const timeLabel = `${dd}.${mm}.${yyyy} ${hh}:${min}`;
    const fileTimestamp = `${yyyy}-${mm}-${dd}_${hh}-${min}`;

    const payload = {
      version: 2,
      app: "ESL FigmaAI",
      type: "board_backup",
      scope: isSelection ? "selection" : "full",
      boardTitle: figma.root.name || "Untitled Board",
      backupTime: timeLabel,
      count: serializedNodes.length,
      mediaCount: mediaCollector ? mediaCollector.files.length : 0,
      timestamp: Date.now(),
      nodes: serializedNodes
    };

    const prefix = isSelection ? "selection_backup" : "board_backup";
    const fileName = isSplit
      ? (isZip ? `${prefix}_${fileTimestamp}.zip` : `${prefix}_${fileTimestamp}`)
      : `${prefix}_${fileTimestamp}.json`;

    figma.ui.postMessage({
      type: "BOARD_EXPORTED_DATA",
      format: isSplit ? "split" : "single",
      scope: isSelection ? "selection" : "full",
      isZip: isZip,
      backupData: payload,
      mediaFiles: mediaCollector ? mediaCollector.files : [],
      fileName: fileName,
      count: serializedNodes.length,
      mediaCount: mediaCollector ? mediaCollector.files.length : 0,
      time: timeLabel
    });

    const mediaNote = (mediaCollector && mediaCollector.files.length > 0) ? ` + ${mediaCollector.files.length} медиа` : "";
    const doneMsg = isSelection ? "Бэкап выделенного сформирован" : "Бэкап доски сформирован";
    figma.notify(`💾 ${doneMsg}: ${serializedNodes.length} эл.${mediaNote}`, { timeout: 2500 });
    return { success: true, count: serializedNodes.length, fileName: fileName };
  } catch (err) {
    console.error("exportBoardToFile error:", err);
    figma.notify("❌ Ошибка при экспорте: " + (err.message || String(err)), { timeout: 3000 });
    return { success: false, error: String(err) };
  }
}

async function restoreBoardFromData(payload, mediaMap = null) {
  try {
    if (!payload || (!payload.nodes && !Array.isArray(payload))) {
      figma.notify("⚠️ Некорректный формат файла бэкапа", { timeout: 3000 });
      figma.ui.postMessage({ type: "BACKUP_RESTORED", success: false });
      return { success: false, reason: "invalid_format" };
    }

    const nodesData = Array.isArray(payload) ? payload : (payload.nodes || []);
    const dateStr = payload.backupTime || "из файла";
    const isSelectionBackup = payload && payload.scope === "selection";

    const notifyMsg = isSelectionBackup
      ? "🔄 Восстановление выделенных элементов..."
      : "🔄 Восстановление доски из бэкапа...";
    figma.notify(notifyMsg, { timeout: 2500 });

    if (!isSelectionBackup) {
      // 1. Очищаем текущие элементы на холсте только при восстановлении всей доски
      const currentNodes = Array.from(figma.currentPage.children);
      for (const n of currentNodes) {
        try { n.remove(); } catch (_) {}
      }
    }

    // 2. Восстанавливаем каждый узел
    const restoredNodes = [];
    for (const nodeData of nodesData) {
      const rn = await deserializeNode(nodeData, figma.currentPage, mediaMap);
      if (rn) restoredNodes.push(rn);
    }

    if (restoredNodes.length > 0) {
      try {
        figma.currentPage.selection = restoredNodes;
        figma.viewport.scrollAndZoomIntoView(restoredNodes);
      } catch (_) {}

      // Также создаем клон-кэш для быстрого доступа
      await createBoardBackup();

      const mediaStr = (mediaMap && Object.keys(mediaMap).length > 0) ? ` + ${Object.keys(mediaMap).length} фото` : "";
      const successTitle = isSelectionBackup ? "Выделенные элементы восстановлены" : "Доска успешно восстановлена";
      figma.notify(`✅ ${successTitle}: ${restoredNodes.length} эл.${mediaStr}! (${dateStr})`, { timeout: 3500 });

      figma.ui.postMessage({
        type: "BACKUP_RESTORED",
        success: true,
        count: restoredNodes.length,
        time: dateStr,
        isSelection: isSelectionBackup,
        fromFile: true
      });

      const tocStat = getTOCStatus();
      figma.ui.postMessage({
        type: "TOC_STATUS",
        exists: tocStat.exists,
        isVisible: tocStat.isVisible
      });

      sendBackupStatus();
      return { success: true, count: restoredNodes.length };
    } else {
      figma.notify("⚠️ Не удалось восстановить элементы из файла", { timeout: 3000 });
      figma.ui.postMessage({ type: "BACKUP_RESTORED", success: false });
      return { success: false, reason: "restore_failed" };
    }
  } catch (err) {
    console.error("restoreBoardFromData error:", err);
    figma.notify("❌ Ошибка восстановления из файла: " + err.message, { timeout: 3000 });
    figma.ui.postMessage({ type: "BACKUP_RESTORED", success: false });
    return { success: false, error: String(err) };
  }
}

let lastSelectedImageId = null;

function sendSelectionInfo() {
  try {
    const sel = figma.currentPage.selection;
    if (!sel || sel.length === 0) {
      figma.ui.postMessage({
        type: "SELECTION_INFO",
        count: 0,
        name: "",
        isImage: false,
        isBlock: false,
        canSaveTemplate: false
      });
      return;
    }
    const node = sel[0];
    const role = (node.getPluginData ? node.getPluginData('role') : '') || '';
    const isBlock = (node.type === 'GROUP' || node.type === 'SECTION' || node.type === 'FRAME') && (role !== '');

    // Check if node is part of TOC navigation
    const isToc = (role === 'table_of_contents' || role === 'toc_item' || role === 'toc_header' || role === 'back_to_menu' || (typeof isInsideTOC === 'function' && isInsideTOC(node)));

    // Treat any non-TOC element on the canvas as an image candidate for VisionAgent
    let isImage = !isToc;
    if (role === 'cat_cover' || role === 'reset_cats' || role === 'reset_quiz') {
      isImage = false;
    }

    if (isImage) {
      lastSelectedImageId = node.id;
    }

    let text = '';
    if (node.characters) text = node.characters;
    else if (node.text && node.text.characters) text = node.text.characters;

    let displayName = (node.name || '').trim();
    if (!displayName || ['Rectangle', 'Media', 'Image', 'Node', 'Shape', 'Group', 'Frame'].includes(displayName)) {
      displayName = isImage ? 'Картинка на доске' : 'Выделенный объект';
    }

    figma.ui.postMessage({
      type: "SELECTION_INFO",
      count: sel.length,
      id: node.id,
      name: displayName,
      type: node.type,
      role: role,
      text: text ? text.slice(0, 100) : '',
      isBlock: isBlock,
      isImage: isImage,
      canSaveTemplate: isBlock,
      width: Math.round(node.width || 0),
      height: Math.round(node.height || 0),
    });

    if (isImage) {
      figma.notify("🖼️ Картинка выбрана: " + displayName, { timeout: 1200 });
    }
  } catch (e) {
    console.warn("sendSelectionInfo error:", e);
  }
}
sendSelectionInfo();

// ── Interactive Handler for FigJam / Figma Boards ──────────────────────────
async function handleInteractiveSelection() {
  try {
    const sel = figma.currentPage.selection;
    if (!sel || sel.length === 0) return;
    const node = sel[0];
    if (!node) return;

    function getRole(n) {
      if (!n) return '';
      return (n.getPluginData ? n.getPluginData('role') : '') || '';
    }

    const nodeRole = getRole(node);
    const parentRole = getRole(node.parent);
    const isReset = nodeRole === 'reset_interactive' || parentRole === 'reset_interactive' ||
      nodeRole === 'reset_cats' || parentRole === 'reset_cats' ||
      (node.name && (node.name.includes('СБРОС') || node.name.includes('ЗАКРЫТЬ ВСЕХ'))) ||
      (node.parent && node.parent.name && (node.parent.name.includes('СБРОС') || node.parent.name.includes('ЗАКРЫТЬ ВСЕХ')));

    // ── 1. RESET BUTTON CLICKED (STRICTLY LOCAL SUB-BLOCK SCOPE) ────────────
    if (isReset) {
      const blockId = node.getPluginData('blockId') ||
        (node.parent && node.parent.getPluginData('blockId')) || '';

      // Find the immediate activity sub-block, NEVER climb to outer full lesson!
      // Start at node.parent so we don't accidentally match the reset button itself!
      let subBlock = node.parent;
      while (subBlock && subBlock.parent && subBlock.parent.type !== 'PAGE' && subBlock.parent.type !== 'DOCUMENT') {
        const r = getRole(subBlock);
        const pr = getRole(subBlock.parent);
        // If subBlock is explicitly an activity block, or its parent is the master lesson container, STOP!
        if (r === 'esl_activity_block' || (subBlock.name && subBlock.name.includes('Interactive Block')) || (blockId && subBlock.getPluginData && subBlock.getPluginData('blockId') === blockId)) {
          break;
        }
        if (pr === 'full_lesson' || (subBlock.parent.name && subBlock.parent.name.includes('🌟 УРОК'))) {
          break;
        }
        subBlock = subBlock.parent;
      }

      const activeBlockId = blockId || (subBlock && subBlock.getPluginData && subBlock.getPluginData('blockId')) || '';

      // 1. Gather all nodes associated with this specific blockId across the canvas
      let allBlockNodes = [];
      if (activeBlockId) {
        try {
          allBlockNodes = figma.currentPage.findAll(n => n.getPluginData && n.getPluginData('blockId') === activeBlockId);
        } catch (e) { }
      }

      // 2. Identify the current container background (reference anchor)
      let bgNode = null;
      if (subBlock && subBlock.children) {
        bgNode = subBlock.children.find(c => {
          const r = getRole(c);
          return r === 'block_container' || (c.name && c.name.includes('Container Background'));
        });
      }
      if (!bgNode && allBlockNodes.length > 0) {
        bgNode = allBlockNodes.find(c => {
          const r = getRole(c);
          return r === 'block_container' || (c.name && c.name.includes('Container Background'));
        });
      }
      const currBlockX = bgNode ? bgNode.x : ((subBlock && typeof subBlock.x === 'number') ? subBlock.x : node.x);
      const currBlockY = bgNode ? bgNode.y : ((subBlock && typeof subBlock.y === 'number') ? subBlock.y : node.y);
      const currBlockW = bgNode ? bgNode.width : ((subBlock && typeof subBlock.width === 'number') ? subBlock.width : 740);

      let count = 0;
      const seenIds = new Set();

      function resetSingleNode(n) {
        if (!n || seenIds.has(n.id)) return;
        seenIds.add(n.id);
        const r = getRole(n);

        if (r === 'quiz_option') {
          const defFill = n.getPluginData('defaultFill') || '#ffffff';
          const defStroke = n.getPluginData('defaultStroke') || '#64748b';
          const defWeight = parseFloat(n.getPluginData('defaultStrokeWeight') || '2.0');
          n.fills = [{ type: 'SOLID', color: hexToRgb(defFill) }];
          n.strokes = [{ type: 'SOLID', color: hexToRgb(defStroke) }];
          n.strokeWeight = defWeight;
          n.setPluginData('state', 'initial');
          count++;
        }
        if (r === 'quiz_option_text') {
          try {
            n.fills = [{ type: 'SOLID', color: hexToRgb('#000000') }]; // Pure Black text on reset
          } catch (e) { }
        }
        if (r === 'cat_cover' || r === 'peek_cover') {
          n.visible = true;
          n.opacity = 1.0;
          n.setPluginData('state', 'covered');
          count++;
        }
        if (r === 'draggable_word_chip') {
          const initRelX = parseFloat(n.getPluginData('initialRelX'));
          const initRelY = parseFloat(n.getPluginData('initialRelY'));
          const initX = parseFloat(n.getPluginData('initialX'));
          const initY = parseFloat(n.getPluginData('initialY'));

          let targetX = initX;
          let targetY = initY;
          if (!isNaN(initRelX) && !isNaN(initRelY)) {
            targetX = currBlockX + initRelX;
            targetY = currBlockY + initRelY;
          } else if (!isNaN(initX) && !isNaN(initY)) {
            // Delta for legacy blocks
            const allChips = allBlockNodes.filter(x => getRole(x) === 'draggable_word_chip');
            const minInitX = allChips.length > 0 ? Math.min(...allChips.map(c => parseFloat(c.getPluginData('initialX')))) : initX;
            const minInitY = allChips.length > 0 ? Math.min(...allChips.map(c => parseFloat(c.getPluginData('initialY')))) : initY;
            const dx = currBlockX - (minInitX - 48);
            const dy = currBlockY - (minInitY - 210);
            targetX = initX + dx;
            targetY = initY + dy;
          }

          n.x = targetX;
          n.y = targetY;
          if (subBlock && (subBlock.type === 'GROUP' || subBlock.type === 'FRAME')) {
            try { subBlock.appendChild(n); } catch (e) { }
          }
          count++;
        }
        if (r === 'speaking_card') {
          const initRelX = parseFloat(n.getPluginData('initialRelX'));
          const initRelY = parseFloat(n.getPluginData('initialRelY'));
          const initRot = parseFloat(n.getPluginData('initialRotation'));
          const cardIdx = parseFloat(n.getPluginData('cardIndex') || '0');
          const offset = (!isNaN(cardIdx) ? cardIdx : 0) * 8;
          const cardW = n.width || 460;

          let targetX, targetY;
          if (!isNaN(initRelX) && !isNaN(initRelY)) {
            targetX = currBlockX + initRelX;
            targetY = currBlockY + initRelY;
          } else {
            // Standard pile center relative to current block container position
            const pileCenterX = currBlockX + (currBlockW - cardW) / 2;
            const cardsStartY = currBlockY + 32 + 72 + 12 + 60; // = currBlockY + 176
            targetX = pileCenterX + offset;
            targetY = cardsStartY + offset;
          }

          n.x = targetX;
          n.y = targetY;
          if (!isNaN(initRot)) n.rotation = initRot;

          if (subBlock && (subBlock.type === 'GROUP' || subBlock.type === 'FRAME') && n.parent && n.parent.id !== subBlock.id) {
            try { subBlock.appendChild(n); } catch (e) { }
          }
          count++;
        }
        if (r === 'answer_text') {
          n.visible = false;
          count++;
        }
        if (n.children && n.children.length) {
          for (const c of n.children) resetSingleNode(c);
        }
      }

      // First reset all nodes discovered by activeBlockId (including external detached cards!)
      for (const bn of allBlockNodes) {
        resetSingleNode(bn);
      }

      // If activeBlockId was present, only reset nodes within subBlock matching activeBlockId
      if (subBlock) {
        if (!activeBlockId) {
          resetSingleNode(subBlock);
        } else {
          // Reset subBlock children that share activeBlockId or are inside subBlock
          function resetScopedChildren(parent) {
            if (!parent || !parent.children) return;
            for (const c of parent.children) {
              const cBid = c.getPluginData ? c.getPluginData('blockId') : '';
              if (!cBid || cBid === activeBlockId) {
                resetSingleNode(c);
              }
            }
          }
          resetScopedChildren(subBlock);
        }
      }

      // 3. Restore correct z-order for Speaking Cards stack in local subBlock!
      if (subBlock && (subBlock.type === 'GROUP' || subBlock.type === 'FRAME')) {
        const speakingCards = (subBlock.children || []).filter(c => getRole(c) === 'speaking_card' && (!activeBlockId || c.getPluginData('blockId') === activeBlockId));
        if (speakingCards.length > 1) {
          speakingCards.sort((a, b) => {
            const idxA = parseInt(a.getPluginData('cardIndex') || '0', 10);
            const idxB = parseInt(b.getPluginData('cardIndex') || '0', 10);
            return idxB - idxA;
          });
          for (const sc of speakingCards) {
            try {
              subBlock.appendChild(sc); // AppendChild moves node to top of group
            } catch (e) { }
          }
        }
      }

      figma.notify('🔄 Упражнение сброшено в исходное состояние!', { timeout: 2000 });
      return;
    }

    // ── 2. QUIZ OPTION CLICKED ────────────────────────────────────────────
    const isQuizOpt = nodeRole === 'quiz_option' || nodeRole === 'quiz_option_container' || nodeRole === 'quiz_option_text' ||
      parentRole === 'quiz_option_container' || parentRole === 'quiz_option';

    if (isQuizOpt) {
      let optRect = null;
      let checkNode = node;

      if (node.type === 'RECTANGLE' && getRole(node) === 'quiz_option') {
        optRect = node;
      } else if (node.type === 'GROUP' || node.type === 'FRAME') {
        optRect = node.children.find(c => c.type === 'RECTANGLE');
      } else if (node.parent && (node.parent.type === 'GROUP' || node.parent.type === 'FRAME')) {
        optRect = node.parent.children.find(c => c.type === 'RECTANGLE');
        checkNode = node.parent;
      }

      if (optRect) {
        const isCorrect = (checkNode.getPluginData('isCorrect') === 'true') ||
          (optRect.getPluginData('isCorrect') === 'true');

        if (isCorrect) {
          // Emerald-500 #10b981
          optRect.fills = [{ type: 'SOLID', color: hexToRgb('#10b981') }];
          optRect.strokes = [{ type: 'SOLID', color: hexToRgb('#059669') }];
          optRect.strokeWeight = 2.5;
          optRect.setPluginData('state', 'correct');
          try {
            if (checkNode.children) {
              const txt = checkNode.children.find(c => c.type === 'TEXT');
              if (txt) txt.fills = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1 } }];
            }
          } catch (e) { }
          figma.notify('🎉 Правильно! Отличный ответ!', { timeout: 1800 });
        } else {
          // Red-500 #ef4444
          optRect.fills = [{ type: 'SOLID', color: hexToRgb('#ef4444') }];
          optRect.strokes = [{ type: 'SOLID', color: hexToRgb('#dc2626') }];
          optRect.strokeWeight = 2.5;
          optRect.setPluginData('state', 'wrong');
          try {
            if (checkNode.children) {
              const txt = checkNode.children.find(c => c.type === 'TEXT');
              if (txt) txt.fills = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1 } }];
            }
          } catch (e) { }
          figma.notify('❌ Неверно. Попробуйте еще раз!', { timeout: 1800 });
        }
      }
      return;
    }

    // ── 3. CAT COVER / PEEK CLICKED ───────────────────────────────────────
    const isCatCover = nodeRole === 'cat_cover' || parentRole === 'cat_cover' ||
      (node.name && node.name.includes('Cat Cover')) ||
      (node.parent && node.parent.name && node.parent.name.includes('Cat Cover'));

    if (isCatCover) {
      let coverRect = (node.type === 'RECTANGLE' ? node : (node.parent && node.parent.type === 'GROUP' ? node.parent.children.find(c => c.type === 'RECTANGLE') : null));
      if (coverRect) {
        coverRect.opacity = 0.05;
        coverRect.setPluginData('state', 'revealed');
        figma.notify('🐱 Секрет открыт!', { timeout: 1500 });
      }
      return;
    }

    // ── 4. QUESTION CARD CLICK (FLIP BACK CLOSED) ──────────────────────────
    const isQuestionCard = nodeRole === 'question_card' || parentRole === 'question_card' ||
      (node.name && node.name.includes('Question Card')) ||
      (node.parent && node.parent.name && node.parent.name.includes('Question Card'));
    if (isQuestionCard) {
      const cardId = node.getPluginData('card_id') || (node.parent && node.parent.getPluginData('card_id')) || '';
      let block = node;
      while (block && block.parent && block.parent !== figma.currentPage) {
        block = block.parent;
      }
      const root = (block && typeof block.findAll === 'function') ? block : figma.currentPage;
      const covers = root.findAll(c => (c.getPluginData && c.getPluginData('role') === 'cat_cover') || (c.name && c.name.includes('Cat Cover')));
      let matchingCover = null;
      if (cardId) {
        matchingCover = covers.find(c => c.getPluginData && c.getPluginData('card_id') === cardId);
      }
      if (!matchingCover && covers.length > 0) {
        matchingCover = covers.find(c => Math.abs(c.x - node.x) < 50 && Math.abs(c.y - node.y) < 50);
      }
      if (matchingCover) {
        matchingCover.visible = true;
        matchingCover.opacity = 1.0;
        figma.currentPage.selection = [];
        figma.notify('🔄 Карточка закрыта!', { timeout: 1200 });
        return;
      }
    }

    // ── 5. BACK TO MENU BUTTON ────────────────────────────────────────────
    const isBackToMenu = nodeRole === 'back_to_menu' || parentRole === 'back_to_menu' ||
      (node.name && node.name.includes('В МЕНЮ')) ||
      (node.parent && node.parent.name && node.parent.name.includes('В МЕНЮ'));
    if (isBackToMenu) {
      await navigateToTableOfContents();
      return;
    }

    // ── 6. TOC NAVIGATION ITEM (CLICK TO GO TO ACTIVITY) ──────────────────
    let checkToc = node;
    let tocItemNode = null;
    while (checkToc && checkToc !== figma.currentPage) {
      if (checkToc.getPluginData && checkToc.getPluginData('role') === 'toc_item') {
        tocItemNode = checkToc;
        break;
      }
      checkToc = checkToc.parent;
    }
    if (tocItemNode) {
      const targetId = tocItemNode.getPluginData('target_id');
      const target = (targetId && figma.getNodeById(targetId)) ||
        figma.currentPage.children.find(c => tocItemNode.name.includes(c.name.split('•')[0].trim()));
      if (target) {
        figma.currentPage.selection = [target];
        figma.viewport.scrollAndZoomIntoView([target]);
        figma.notify('🚀 Переход к: ' + (tocItemNode.getPluginData('target_title') || target.name.slice(0, 30)), { timeout: 2000 });
      }
      return;
    }

  } catch (e) {
    console.warn("Interactive selection error:", e);
  }
}

figma.on("selectionchange", () => {
  sendSelectionInfo();
  handleInteractiveSelection();
});



function hexToRgb(hex) {
  if (!hex) return { r: 0.5, g: 0.5, b: 0.5 };
  hex = hex.replace("#", "").trim();
  if (hex.length === 3) {
    hex = hex.split("").map(c => c + c).join("");
  }
  const num = parseInt(hex, 16);
  if (isNaN(num)) return { r: 0.5, g: 0.5, b: 0.5 };
  return {
    r: ((num >> 16) & 255) / 255,
    g: ((num >> 8) & 255) / 255,
    b: (num & 255) / 255
  };
}

let fontsLoaded = false;
async function ensureFonts() {
  if (fontsLoaded) return;
  try {
    await Promise.all([
      figma.loadFontAsync({ family: "Inter", style: "Regular" }),
      figma.loadFontAsync({ family: "Inter", style: "Medium" }),
      figma.loadFontAsync({ family: "Inter", style: "Bold" })
    ]);
    fontsLoaded = true;
  } catch (e) {
    console.warn("Font loading fallback:", e);
  }
}

function getViewportCenter(width = 160, height = 160) {
  try {
    const vp = figma.viewport.center;
    return {
      x: Math.round(vp.x - width / 2),
      y: Math.round(vp.y - height / 2)
    };
  } catch (e) {
    return { x: 0, y: 0 };
  }
}

function isNodeValidForCanvasBounds(child) {
  if (!child) return false;
  if (child.visible === false) return false;
  if (child.getPluginData && child.getPluginData("role") === "board_backup") return false;
  if (child.name && (child.name.startsWith("🔒 [РЕЗЕРВНАЯ КОПИЯ") || child.name.startsWith("🔒 [БЭКАП") || child.name.includes("РЕЗЕРВНАЯ КОПИЯ"))) return false;
  if (typeof child.x !== "number" || typeof child.y !== "number") return false;
  if (isNaN(child.x) || isNaN(child.y)) return false;
  // Discard crazy outliers (e.g. backup or test nodes placed at -999999 or distant infinity)
  if (child.x < -40000 || child.x > 400000 || child.y < -40000 || child.y > 400000) return false;
  return true;
}

function getCanvasBounds() {
  const children = figma.currentPage.children;
  if (!children || children.length === 0) return null;

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  let hasValid = false;

  for (const child of children) {
    if (isNodeValidForCanvasBounds(child)) {
      const w = Math.max(0, child.width || 0);
      const h = Math.max(0, child.height || 0);
      minX = Math.min(minX, child.x);
      minY = Math.min(minY, child.y);
      maxX = Math.max(maxX, child.x + w);
      maxY = Math.max(maxY, child.y + h);
      hasValid = true;
    }
  }

  return hasValid ? { minX, minY, maxX, maxY, width: maxX - minX, height: maxY - minY } : null;
}

function findSmartNonOverlappingPosition(width = 180, height = 180, placement = "AUTO") {
  const gap = 100;
  
  // 1. Priority 1: User's explicit canvas selection
  const sel = figma.currentPage.selection || [];
  const validSel = sel.filter(isNodeValidForCanvasBounds);
  if (validSel.length > 0) {
    let sMinX = Infinity, sMinY = Infinity, sMaxX = -Infinity, sMaxY = -Infinity;
    for (const n of validSel) {
      sMinX = Math.min(sMinX, n.x);
      sMinY = Math.min(sMinY, n.y);
      sMaxX = Math.max(sMaxX, n.x + (n.width || 0));
      sMaxY = Math.max(sMaxY, n.y + (n.height || 0));
    }
    if (placement === "BOTTOM") {
      return { x: Math.round(sMinX), y: Math.round(sMaxY + gap) };
    }
    return { x: Math.round(sMaxX + gap), y: Math.round(sMinY) };
  }

  // 2. Priority 2: Teacher's active Viewport
  let vp = null;
  try {
    if (figma.viewport && figma.viewport.center) {
      vp = {
        x: figma.viewport.center.x,
        y: figma.viewport.center.y,
        zoom: figma.viewport.zoom || 1
      };
    }
  } catch (_) {}

  if (vp && !isNaN(vp.x) && !isNaN(vp.y) && vp.x > -40000 && vp.x < 400000 && vp.y > -40000 && vp.y < 400000) {
    const validChildren = (figma.currentPage.children || []).filter(isNodeValidForCanvasBounds);
    
    // Find valid nodes near viewport center (within 3000px)
    const nearNodes = validChildren.filter(n => {
      const cx = n.x + (n.width || 0) / 2;
      const cy = n.y + (n.height || 0) / 2;
      return Math.hypot(cx - vp.x, cy - vp.y) < 3000;
    });

    if (nearNodes.length > 0) {
      // Find the rightmost node in this viewport cluster
      let rightmost = nearNodes[0];
      for (const n of nearNodes) {
        if ((n.x + (n.width || 0)) > (rightmost.x + (rightmost.width || 0))) {
          rightmost = n;
        }
      }
      if (placement === "BOTTOM") {
        let bottommost = nearNodes[0];
        for (const n of nearNodes) {
          if ((n.y + (n.height || 0)) > (bottommost.y + (bottommost.height || 0))) {
            bottommost = n;
          }
        }
        return {
          x: Math.round(bottommost.x),
          y: Math.round(bottommost.y + (bottommost.height || 0) + gap)
        };
      }
      return {
        x: Math.round(rightmost.x + (rightmost.width || 0) + gap),
        y: Math.round(rightmost.y)
      };
    }

    // If no nodes near viewport center, place directly in the center of the teacher's screen!
    return {
      x: Math.round(vp.x - width / 2),
      y: Math.round(vp.y - height / 2)
    };
  }

  // 3. Priority 3: Fallback to existing ESL blocks on the canvas
  const eslBlocks = (figma.currentPage.children || []).filter(n =>
    isNodeValidForCanvasBounds(n) && (
      (n.getPluginData && n.getPluginData("role") === "esl_activity_block") ||
      (n.type === "GROUP" && n.name && (n.name.includes("Interactive Block") || n.name.includes("Quiz") || n.name.includes("Lesson") || n.name.includes("УРОК")))
    )
  );

  if (eslBlocks.length > 0) {
    let lastBlock = eslBlocks[0];
    for (const b of eslBlocks) {
      if ((b.x + (b.width || 0)) > (lastBlock.x + (lastBlock.width || 0))) {
        lastBlock = b;
      }
    }
    return {
      x: Math.round(lastBlock.x + (lastBlock.width || 0) + gap),
      y: Math.round(lastBlock.y)
    };
  }

  // 4. Global bounds fallback
  const bounds = getCanvasBounds();
  if (bounds) {
    if (placement === "BOTTOM" || width >= 500) {
      return {
        x: Math.round(bounds.minX),
        y: Math.round(bounds.maxY + gap)
      };
    }
    return {
      x: Math.round(bounds.maxX + gap),
      y: Math.round((bounds.minY + bounds.maxY) / 2 - height / 2)
    };
  }

  return getViewportCenter(width, height);
}

function connectNodes(fromNode, toNode, startMagnet = "BOTTOM", endMagnet = "TOP") {
  if (typeof figma.createConnector !== "function") return null;
  try {
    const conn = figma.createConnector();
    conn.connectorStart = {
      endpointNodeId: fromNode.id,
      magnet: startMagnet
    };
    conn.connectorEnd = {
      endpointNodeId: toNode.id,
      magnet: endMagnet
    };
    conn.connectorLineType = "ELBOWED";
    return conn;
  } catch (e) {
    return null;
  }
}

async function createShapeOnCanvas(params = {}) {
  await ensureFonts();
  const shapeType = (params.shapeType || "ROUNDED_RECTANGLE").toUpperCase();
  const width = params.width || params.size || 180;
  const height = params.height || params.size || 180;
  const colorHex = params.color || (shapeType === "ELLIPSE" ? "#8b5cf6" : "#3b82f6");
  const textColorHex = params.textColor || "#ffffff";
  const text = params.text !== undefined ? String(params.text) : "";

  // Smart non-overlapping position
  const smartPos = findSmartNonOverlappingPosition(width, height);
  const x = params.x !== undefined ? params.x : smartPos.x;
  const y = params.y !== undefined ? params.y : smartPos.y;

  let node;
  const isFigJam = typeof figma.createShapeWithText === "function";

  if (shapeType === "STICKY" && typeof figma.createSticky === "function") {
    const sticky = figma.createSticky();
    sticky.x = x;
    sticky.y = y;
    if (text) {
      try { sticky.text.characters = text; } catch (e) { }
    }
    node = sticky;
  } else if (isFigJam) {
    const shape = figma.createShapeWithText();
    const validTypes = ["SQUARE", "ELLIPSE", "ROUNDED_RECTANGLE", "DIAMOND", "TRIANGLE_UP", "TRIANGLE_DOWN", "PARALLELOGRAM_RIGHT", "PARALLELOGRAM_LEFT"];
    shape.shapeType = validTypes.includes(shapeType) ? shapeType : "ROUNDED_RECTANGLE";
    shape.resize(width, height);
    shape.x = x;
    shape.y = y;
    if (colorHex) {
      shape.fills = [{ type: "SOLID", color: hexToRgb(colorHex) }];
    }
    if (text) {
      try {
        shape.text.fontName = { family: "Inter", style: "Medium" };
        shape.text.characters = text;
        try { shape.text.fontSize = params.fontSize || 15; } catch (fe) { }
        if (textColorHex) {
          shape.text.fills = [{ type: "SOLID", color: hexToRgb(textColorHex) }];
        }
      } catch (te) { }
    }
    node = shape;
  } else {
    if (shapeType === "ELLIPSE") {
      node = figma.createEllipse();
    } else {
      node = figma.createRectangle();
      if (shapeType === "ROUNDED_RECTANGLE") {
        node.cornerRadius = 12;
      }
    }
    node.resize(width, height);
    node.x = x;
    node.y = y;
    if (colorHex) {
      node.fills = [{ type: "SOLID", color: hexToRgb(colorHex) }];
    }
    figma.currentPage.appendChild(node);
  }

  try {
    figma.currentPage.selection = [node];
  } catch (e) { }

  const label = shapeType === "ELLIPSE" ? "Круг" : shapeType === "STICKY" ? "Стикер" : "Фигура";
  figma.notify(`✅ ${label} добавлен и выделен! Перетащите его в нужное место.`, { timeout: 2500 });
  return { success: true, nodeId: node.id, type: node.type, x: node.x, y: node.y };
}

async function drawEnglishVocabularyAndQuiz() {
  await ensureFonts();
  const isFigJam = typeof figma.createShapeWithText === "function";
  const createdNodes = [];

  function makeShape(text, x, y, w, h, colorHex, textColorHex = "#ffffff", fontSize = 13, shapeType = "ROUNDED_RECTANGLE") {
    let shape;
    if (isFigJam) {
      shape = figma.createShapeWithText();
      shape.shapeType = shapeType;
      shape.resize(w, h);
      shape.x = x;
      shape.y = y;
      if (colorHex) shape.fills = [{ type: "SOLID", color: hexToRgb(colorHex) }];
      if (text) {
        try {
          shape.text.fontName = { family: "Inter", style: "Medium" };
          shape.text.characters = text;
          try { shape.text.fontSize = fontSize; } catch (e) { }
          if (textColorHex) shape.text.fills = [{ type: "SOLID", color: hexToRgb(textColorHex) }];
        } catch (e) { }
      }
    } else {
      shape = figma.createRectangle();
      shape.resize(w, h);
      shape.x = x;
      shape.y = y;
      shape.cornerRadius = 8;
      if (colorHex) shape.fills = [{ type: "SOLID", color: hexToRgb(colorHex) }];
      figma.currentPage.appendChild(shape);
    }
    createdNodes.push(shape);
    return shape;
  }

  // Calculate safe non-overlapping origin point for the new block
  const origin = findSmartNonOverlappingPosition(2220, 800, "BOTTOM");
  const baseX = origin.x;
  const baseY = origin.y;

  // 1. Big Title Banner
  makeShape(
    "🇬🇧 ENGLISH VOCABULARY & INTERACTIVE QUIZ • 10 ESSENTIAL WORDS",
    baseX, baseY, 2220, 65,
    "#0f172a", "#ffffff", 18
  );

  // 2. Left Column: Table of 10 Words
  const tableY = baseY + 85;
  makeShape("📚 ТАБЛИЦА СЛОВАРЯ (10 КЛЮЧЕВЫХ СЛОВ B2-C1)", baseX, tableY, 1040, 45, "#312e81", "#c7d2fe", 14);

  // Headers
  const headerY = tableY + 55;
  makeShape("СЛОВО", baseX, headerY, 200, 38, "#4338ca", "#ffffff", 12);
  makeShape("ТРАНСКРИПЦИЯ", baseX + 205, headerY, 215, 38, "#4338ca", "#ffffff", 12);
  makeShape("ПЕРЕВОД", baseX + 425, headerY, 240, 38, "#4338ca", "#ffffff", 12);
  makeShape("ПРИМЕР В КОНТЕКСТЕ", baseX + 670, headerY, 370, 38, "#4338ca", "#ffffff", 12);

  const words = [
    { w: "Resilient", tr: "[rɪˈzɪl.jənt] • adj.", ru: "Стойкий, упругий", ex: "She is remarkably resilient under stress." },
    { w: "Serendipity", tr: "[ˌser.ənˈdɪp.ə.ti] • n.", ru: "Счастливый случай", ex: "Finding this job was pure serendipity." },
    { w: "Meticulous", tr: "[məˈtɪk.jə.ləs] • adj.", ru: "Тщательный, педантичный", ex: "He takes meticulous care of his work." },
    { w: "Inevitable", tr: "[ɪnˈev.ɪ.tə.bəl] • adj.", ru: "Неизбежный, фатальный", ex: "Rapid change is inevitable in technology." },
    { w: "Eloquent", tr: "[ˈel.ə.kwənt] • adj.", ru: "Красноречивый", ex: "She made an eloquent speech at the event." },
    { w: "Perseverance", tr: "[ˌpɜː.sɪˈvɪə.rəns] • n.", ru: "Упорство, настойчивость", ex: "Success requires patience and perseverance." },
    { w: "Empathetic", tr: "[ˌem.pəˈθet.ɪk] • adj.", ru: "Чуткий, сопереживающий", ex: "A great leader is deeply empathetic." },
    { w: "Ubiquitous", tr: "[juːˈbɪk.wɪ.təs] • adj.", ru: "Вездесущий, повсеместный", ex: "Smartphones are now ubiquitous worldwide." },
    { w: "Pragmatic", tr: "[præɡˈmæt.ɪk] • adj.", ru: "Прагматичный, практичный", ex: "We adopted a pragmatic approach to the issue." },
    { w: "Lucid", tr: "[ˈluː.sɪd] • adj.", ru: "Ясный, понятный", ex: "The professor gave a very lucid explanation." }
  ];

  let startY = headerY + 45;
  words.forEach((item, idx) => {
    const rowY = startY + idx * 46;
    const bg = idx % 2 === 0 ? "#f8fafc" : "#f1f5f9";

    makeShape(item.w, baseX, rowY, 200, 42, "#e0e7ff", "#3730a3", 13);
    makeShape(item.tr, baseX + 205, rowY, 215, 42, bg, "#64748b", 11);
    makeShape(item.ru, baseX + 425, rowY, 240, 42, bg, "#0f172a", 12);
    makeShape(item.ex, baseX + 670, rowY, 370, 42, bg, "#334155", 11);
  });

  // 3. Right Column: Quiz Game Cards
  const quizX = baseX + 1120;
  makeShape("🎮 КВИЗ-ИГРА: КАРТОЧКИ С ВАРИАНТАМИ ОТВЕТОВ", quizX, tableY, 1100, 45, "#065f46", "#a7f3d0", 14);

  const quizCards = [
    {
      q: "🎯 Вопрос 1: Какое слово означает 'стойкий, способный восстанавливаться'?",
      options: [
        { text: "A) Ubiquitous", correct: false },
        { text: "B) Resilient ✅", correct: true },
        { text: "C) Meticulous", correct: false }
      ]
    },
    {
      q: "🎯 Вопрос 2: Что означает английское слово 'Serendipity'?",
      options: [
        { text: "A) Счастливый случай ✅", correct: true },
        { text: "B) Неизбежный финал", correct: false },
        { text: "C) Чуткий совет", correct: false }
      ]
    },
    {
      q: "🎯 Вопрос 3: Найдите верный перевод слова 'Meticulous':",
      options: [
        { text: "A) Поверхностный", correct: false },
        { text: "B) Красноречивый", correct: false },
        { text: "C) Тщательный, дотошный ✅", correct: true }
      ]
    },
    {
      q: "🎯 Вопрос 4: Как переводится слово 'Eloquent'?",
      options: [
        { text: "A) Красноречивый ✅", correct: true },
        { text: "B) Прагматичный", correct: false },
        { text: "C) Вездесущий", correct: false }
      ]
    },
    {
      q: "🎯 Вопрос 5: Какое слово переводится как 'Вездесущий, повсеместный'?",
      options: [
        { text: "A) Lucid", correct: false },
        { text: "B) Ubiquitous ✅", correct: true },
        { text: "C) Inevitable", correct: false }
      ]
    }
  ];

  let qY = headerY;
  quizCards.forEach((card) => {
    const qBox = makeShape(card.q, quizX, qY, 1100, 46, "#1e293b", "#ffffff", 13);
    const optY = qY + 54;
    const optW = 350;
    const gap = 25;

    card.options.forEach((opt, optIdx) => {
      const curX = quizX + optIdx * (optW + gap);
      const optBg = opt.correct ? "#dcfce7" : "#f1f5f9";
      const optTextColor = opt.correct ? "#15803d" : "#334155";
      const optNode = makeShape(opt.text, curX, optY, optW, 40, optBg, optTextColor, 13);
      const conn = connectNodes(qBox, optNode, "BOTTOM", "TOP");
      if (conn) createdNodes.push(conn);
    });

    qY += 105;
  });

  // IMMEDIATELY SELECT ALL CREATED NODES AT ONCE!
  // This allows the user to immediately drag the whole block as one piece!
  try {
    figma.currentPage.selection = [];
  } catch (e) { }

  figma.notify("✅ Весь блок создан и сразу выделен! Можете перемещать его в любое место.", { timeout: 4000 });
  return { success: true, wordCount: words.length, quizCount: quizCards.length, totalNodesCreated: createdNodes.length };
}

async function drawKidsEnglishA1Game() {
  await ensureFonts();
  const isFigJam = typeof figma.createShapeWithText === "function";
  const createdNodes = [];

  async function makeShape(text, x, y, w, h, colorHex, textColorHex = "#ffffff", fontSize = 13, shapeType = "ROUNDED_RECTANGLE") {
    let shape;
    if (isFigJam) {
      shape = figma.createShapeWithText();
      shape.shapeType = shapeType;
      shape.resize(w, h);
      shape.x = x;
      shape.y = y;
      if (colorHex) shape.fills = [{ type: "SOLID", color: hexToRgb(colorHex) }];
      if (text) {
        try {
          await figma.loadFontAsync(shape.text.fontName);
          shape.text.characters = text;
          try { shape.text.fontSize = fontSize; } catch (e) { }
          if (textColorHex) shape.text.fills = [{ type: "SOLID", color: hexToRgb(textColorHex) }];
        } catch (e) {
          console.error("makeShape text error:", e);
        }
      }
    } else {
      shape = figma.createRectangle();
      shape.resize(w, h);
      shape.x = x;
      shape.y = y;
      shape.cornerRadius = 10;
      if (colorHex) shape.fills = [{ type: "SOLID", color: hexToRgb(colorHex) }];
      figma.currentPage.appendChild(shape);
    }
    createdNodes.push(shape);
    return shape;
  }

  // Safe placement below existing blocks
  const totalW = 1450;
  const totalH = 750;
  const origin = findSmartNonOverlappingPosition(totalW, totalH, "BOTTOM");
  const baseX = origin.x;
  const baseY = origin.y;

  // Title Banner
  await makeShape(
    "🧸 ENGLISH A1 FOR KIDS • INTERACTIVE QUIZ GAME! 🌟",
    baseX, baseY, totalW, 60,
    "#0f172a", "#ffffff", 18
  );

  // Instructions
  await makeShape(
    "👉 КЛИКАЙ МЫШКОЙ НА КАРТОЧКИ СПРАВА: ПРАВИЛЬНЫЙ = 🟢 ЗЕЛЁНЫЙ, НЕПРАВИЛЬНЫЙ = 🔴 КРАСНЫЙ!",
    baseX, baseY + 68, totalW - 275, 42,
    "#1e1b4b", "#a5b4fc", 12
  );

  // Interactive Reset Button on Canvas!
  const btnReset = await makeShape(
    "🔄 СБРОСИТЬ ОТВЕТЫ",
    baseX + totalW - 260, baseY + 68, 260, 42,
    "#6366f1", "#ffffff", 13
  );
  btnReset.setPluginData("role", "reset_quiz");

  const questions = [
    {
      q: "🐱 1. What animal says 'Meow' and loves milk?",
      options: [
        { text: "A cute cat 🐱", correct: true },
        { text: "A friendly dog 🐶", correct: false },
        { text: "A big elephant 🐘", correct: false }
      ]
    },
    {
      q: "☀️ 2. What color is the warm sun in the sky?",
      options: [
        { text: "Ocean Blue 🌊", correct: false },
        { text: "Bright Yellow ☀️", correct: true },
        { text: "Forest Green 🍏", correct: false }
      ]
    },
    {
      q: "🍎 3. Which one is a sweet red fruit?",
      options: [
        { text: "An onion 🧅", correct: false },
        { text: "An orange carrot 🥕", correct: false },
        { text: "A red apple 🍎", correct: true }
      ]
    },
    {
      q: "🚗 4. How many wheels does a car have?",
      options: [
        { text: "Two wheels (2)", correct: false },
        { text: "Ten wheels (10)", correct: false },
        { text: "Four wheels (4)", correct: true }
      ]
    },
    {
      q: "🏫 5. Where do children go to learn and read?",
      options: [
        { text: "To the jungle 🌴", correct: false },
        { text: "To school 🏫", correct: true },
        { text: "To the moon 🌙", correct: false }
      ]
    },
    {
      q: "🥛 6. What healthy white drink do cows give us?",
      options: [
        { text: "Orange juice 🍊", correct: false },
        { text: "Cold soup 🍲", correct: false },
        { text: "Fresh milk 🥛", correct: true }
      ]
    }
  ];

  let curY = baseY + 122;
  const questionW = 540;
  const questionH = 56;
  const optW = 270;
  const optH = 50;
  const optGap = 16;
  const optStartX = baseX + questionW + 35;

  // Balanced correct slots: guarantees exactly two A, two B, and two C correct answers!
  const targetSlots = [0, 1, 2, 0, 1, 2];
  for (let i = targetSlots.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [targetSlots[i], targetSlots[j]] = [targetSlots[j], targetSlots[i]];
  }

  for (let qIdx = 0; qIdx < questions.length; qIdx++) {
    const item = questions[qIdx];
    // Left: Question Card
    await makeShape(item.q, baseX, curY, questionW, questionH, "#1e293b", "#f8fafc", 13);

    const targetCorrectSlot = targetSlots[qIdx]; // 0 for A, 1 for B, 2 for C
    const correctOpt = item.options.find(o => o.correct);
    const distractors = item.options.filter(o => !o.correct);
    if (Math.random() > 0.5) distractors.reverse();

    const finalOptions = new Array(3);
    finalOptions[targetCorrectSlot] = correctOpt;
    let dIdx = 0;
    for (let s = 0; s < 3; s++) {
      if (s !== targetCorrectSlot) {
        finalOptions[s] = distractors[dIdx++];
      }
    }

    // Right: 3 Answer Option Cards
    for (let optIdx = 0; optIdx < 3; optIdx++) {
      const opt = finalOptions[optIdx];
      const prefix = String.fromCharCode(65 + optIdx) + ") ";
      const displayText = prefix + opt.text;
      const optX = optStartX + optIdx * (optW + optGap);
      const optNode = await makeShape(displayText, optX, curY + 3, optW, optH, "#1e293b", "#ffffff", 14);
      optNode.strokes = [{ type: "SOLID", color: hexToRgb("#334155") }];
      optNode.strokeWeight = 1.5;

      // Save interactive plugin data for click handling!
      optNode.setPluginData("role", "quiz_option");
      optNode.setPluginData("isCorrect", opt.correct ? "true" : "false");
      optNode.setPluginData("optText", displayText);
    }

    curY += 76;
  }

  try {
    figma.currentPage.selection = [];
  } catch (e) { }

  figma.notify("🎮 Детская игра A1 создана и выделена! Кликайте мышкой по карточкам ответов.", { timeout: 4000 });
  return { success: true, count: questions.length, totalNodesCreated: createdNodes.length };
}

async function clearBoard() {
  let count = 0;
  const children = [...figma.currentPage.children];
  for (const child of children) {
    try {
      child.remove();
      count++;
    } catch (e) { }
  }
  figma.notify(`🧹 Холст очищен (удалено ${count} элементов)`, { timeout: 2500 });
  return { success: true, removedCount: count };
}

function getCanvasInfo() {
  const selection = figma.currentPage.selection.map(n => ({
    id: n.id,
    name: n.name,
    type: n.type,
    width: n.width,
    height: n.height
  }));
  return {
    success: true,
    totalLayers: figma.currentPage.children.length,
    selectedCount: selection.length,
    selection: selection,
    viewport: figma.viewport.center
  };
}

function getBoardIndex() {
  const children = figma.currentPage.children;
  const blocks = [];

  for (const node of children) {
    const act = node.getPluginData ? node.getPluginData("activity") : "";
    const topic = node.getPluginData ? node.getPluginData("topic") : "";
    let text = "";
    try {
      if (node.text && node.text.characters) {
        text = node.text.characters;
      } else if (node.name) {
        text = node.name;
      }
    } catch (e) { }

    const isBanner = (node.height && node.height <= 70 && node.width && node.width >= 350 && (text.includes("•") || text.includes("!")));
    if (isBanner || act) {
      blocks.push({
        id: node.id,
        title: text.split("\n")[0].substring(0, 60),
        activity: act || "custom",
        topic: topic,
        x: Math.round(node.x),
        y: Math.round(node.y),
        width: Math.round(node.width),
        height: Math.round(node.height)
      });
    }
  }

  return {
    success: true,
    totalBlocks: blocks.length,
    boardName: figma.root.name || "Untitled",
    blocks: blocks
  };
}

function findAndZoom(query) {
  if (!query) return { success: false, error: "Укажите поисковый запрос" };
  const rawQuery = String(query).trim();
  const lower = rawQuery.toLowerCase();
  const queryTokens = lower.split(/\s+/).filter(w => w.length >= 2);

  // Search through ALL nodes on the page (including inside groups, frames, sections)
  let allNodes = [];
  try {
    allNodes = figma.currentPage.findAll(() => true);
  } catch (e) {
    allNodes = figma.currentPage.children;
  }

  let bestNode = null;
  let highestScore = 0;
  let matchSnippet = "";

  for (const node of allNodes) {
    let text = "";
    if (node.type === "TEXT" && node.characters) {
      text = node.characters;
    } else if (node.text && node.text.characters) {
      text = node.text.characters;
    }

    const name = node.name || "";
    const act = (node.getPluginData ? node.getPluginData("activity") : "") || "";
    const topic = (node.getPluginData ? node.getPluginData("topic") : "") || "";
    const tags = (node.getPluginData ? node.getPluginData("tags") : "") || "";

    const fullStr = (text + " " + tags + " " + topic + " " + act + " " + name).toLowerCase();

    // Check if query matches anywhere
    if (!fullStr.includes(lower)) {
      let hasToken = false;
      for (const tok of queryTokens) {
        if (fullStr.includes(tok)) { hasToken = true; break; }
      }
      if (!hasToken) continue;
    }

    let score = 0;
    const lowerText = text.toLowerCase();

    // Direct text words on board have HIGHEST priority!
    if (lowerText.includes(lower)) {
      score += 100;
      const regex = new RegExp("(?:^|\\s|[,.!?;:])" + lower.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "(?:$|\\s|[,.!?;:])", "i");
      if (regex.test(lowerText)) score += 50;
    }

    // Matching tags/topics/activity/name
    if (tags && tags.toLowerCase().includes(lower)) score += 80;
    if (topic && topic.toLowerCase().includes(lower)) score += 70;
    if (act && act.toLowerCase().includes(lower)) score += 60;
    if (name.toLowerCase().includes(lower)) score += 40;

    // Multi-word token bonuses
    for (const tok of queryTokens) {
      if (lowerText.includes(tok)) score += 25;
      if (tags && tags.toLowerCase().includes(tok)) score += 20;
    }

    // De-prioritize background containers so focus is on content
    if (name.includes("Background") || name.includes("Container")) {
      score -= 40;
    }

    if (score > highestScore) {
      highestScore = score;
      bestNode = node;
      matchSnippet = text ? text.split("\n")[0].substring(0, 50) : (name || act || topic);
    }
  }

  if (!bestNode) {
    figma.notify("🔍 Ничего не найдено по слову: '" + rawQuery + "'", { timeout: 2500 });
    return { success: false, found: false, error: "Слово не найдено: " + rawQuery };
  }

  // Find enclosing parent group or section
  let target = bestNode;
  let p = bestNode.parent;
  while (p && p.type !== "PAGE") {
    if (p.type === "GROUP" || p.type === "SECTION") {
      target = p;
    }
    p = p.parent;
  }

  try {
    figma.currentPage.selection = [target];
    figma.viewport.scrollAndZoomIntoView([target]);
  } catch (e) {
    figma.currentPage.selection = [bestNode];
    figma.viewport.scrollAndZoomIntoView([bestNode]);
  }

  let title = target.name || bestNode.name;
  figma.notify("🔍 Найдено: «" + matchSnippet + "» (" + title + ")", { timeout: 3500 });

  return {
    success: true,
    found: true,
    title: matchSnippet || title,
    targetName: title,
    nodeId: target.id
  };
}
globalThis.findAndZoom = findAndZoom;

function getEnclosingBlock(node) {
  let curr = node;
  let block = curr;
  while (curr && curr.parent && curr.parent.type !== "PAGE") {
    curr = curr.parent;
    if (curr.type === "GROUP" || curr.type === "SECTION" || curr.type === "FRAME") {
      block = curr;
    }
  }
  if (curr && curr.parent && curr.parent.type === "PAGE") {
    block = curr;
  }
  return block;
}

function searchAllBlocks(query) {
  if (!query) return { success: false, error: "Укажите поисковый запрос", results: [] };
  const rawQuery = String(query).trim();
  const lower = rawQuery.toLowerCase();
  const queryTokens = lower.split(/\s+/).filter(w => w.length >= 2);

  let allNodes = [];
  try {
    allNodes = figma.currentPage.findAll(() => true);
  } catch (e) {
    allNodes = figma.currentPage.children;
  }

  const blockMap = new Map();

  for (const node of allNodes) {
    let text = "";
    if (node.type === "TEXT" && node.characters) text = node.characters;
    else if (node.text && node.text.characters) text = node.text.characters;

    const name = node.name || "";
    const act = (node.getPluginData ? node.getPluginData("activity") : "") || "";
    const topic = (node.getPluginData ? node.getPluginData("topic") : "") || "";
    const tags = (node.getPluginData ? node.getPluginData("tags") : "") || "";

    const fullStr = (text + " " + tags + " " + topic + " " + act + " " + name).toLowerCase();

    let matched = fullStr.includes(lower);
    if (!matched) {
      for (const t of queryTokens) {
        if (fullStr.includes(t)) { matched = true; break; }
      }
    }
    if (!matched) continue;

    const block = getEnclosingBlock(node);
    if (!block || (block.id === node.id && block.type === "PAGE")) continue;

    const isTagNode = name.toLowerCase().includes("tag") || name.toLowerCase().includes("хештег") || (text && text.includes("🏷️"));
    const isBgNode = name.toLowerCase().includes("background") || name.toLowerCase().includes("container") || name.toLowerCase().includes("подложк");

    let score = 0;
    const lowerText = text.toLowerCase();
    const lowerBlockName = (block.name || "").toLowerCase();

    // 1. Direct match in Block Title has top priority
    if (lowerBlockName.includes(lower)) {
      score += 150;
    }

    // 2. Direct match in card text or node text
    if (lowerText.includes(lower)) {
      if (isTagNode) {
        score += 40; // tags provide discovery but don't overshadow content
      } else {
        score += 100;
        const rx = new RegExp("(?:^|\\s|[,.!?;:])" + lower.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&") + "(?:$|\\s|[,.!?;:])", "i");
        if (rx.test(lowerText)) score += 30;
      }
    }

    if (tags && tags.toLowerCase().includes(lower)) score += 35;
    if (topic && topic.toLowerCase().includes(lower)) score += 60;
    if (act && act.toLowerCase().includes(lower)) score += 50;
    if (name.toLowerCase().includes(lower) && !isTagNode && !isBgNode) score += 50;

    for (const t of queryTokens) {
      if (lowerText.includes(t)) score += (isTagNode ? 10 : 20);
    }

    if (isBgNode) score -= 50;

    // Build context snippet
    let snippet = "";
    if (!isTagNode && text) {
      const lines = text.split("\n").map(l => l.trim()).filter(Boolean);
      for (const line of lines) {
        if (line.toLowerCase().includes(lower)) {
          snippet = line;
          break;
        }
      }
      if (!snippet && lines.length > 0) snippet = lines[0];
    } else if (isTagNode && text) {
      snippet = text.split("\n")[0];
    } else if (tags) {
      snippet = "🏷️ " + tags;
    } else {
      snippet = name;
    }
    if (snippet.length > 65) snippet = snippet.substring(0, 63) + "...";

    if (!blockMap.has(block.id)) {
      blockMap.set(block.id, {
        blockId: block.id,
        blockName: block.name || "Блок без названия",
        blockType: block.type,
        snippet: snippet,
        isTagSnippet: isTagNode,
        matchCount: 1,
        bestNodeId: node.id,
        topScore: score
      });
    } else {
      const existing = blockMap.get(block.id);
      existing.matchCount++;
      if (score > existing.topScore) {
        existing.topScore = score;
        existing.bestNodeId = node.id;
      }
      // Prefer non-tag snippet over tag snippet
      if (snippet && (existing.isTagSnippet || !existing.snippet || (!isTagNode && existing.isTagSnippet))) {
        existing.snippet = snippet;
        existing.isTagSnippet = isTagNode;
      }
    }
  }

  const results = Array.from(blockMap.values()).sort((a, b) => b.topScore - a.topScore);
  return {
    success: true,
    query: rawQuery,
    totalBlocks: results.length,
    results: results
  };
}
globalThis.searchAllBlocks = searchAllBlocks;

// ═══════════════════════════════════════════════════
// ESL FIGMA AI — Draw Functions
// ═══════════════════════════════════════════════════


// Shared ESL block helper
async function _eslEnsureFonts() {
  await Promise.all([
    figma.loadFontAsync({ family: 'Inter', style: 'Regular' }),
    figma.loadFontAsync({ family: 'Inter', style: 'Medium' }),
    figma.loadFontAsync({ family: 'Inter', style: 'Bold' }),
  ]);
}

function _eslMakeRect(x, y, w, h, fillHex, cornerRadius = 16) {
  const rect = figma.createRectangle();
  rect.x = x; rect.y = y;
  rect.resize(w, h);
  rect.cornerRadius = cornerRadius;
  if (fillHex) rect.fills = [{ type: 'SOLID', color: hexToRgb(fillHex) }];
  figma.currentPage.appendChild(rect);
  return rect;
}

function base64ToUint8Array(base64) {
  try {
    const raw = base64.replace(/^data:image\/\w+;base64,/, '');
    const bin = atob(raw);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes;
  } catch (e) {
    return null;
  }
}

function _eslMakeText(chars, x, y, w, h, fillHex, fontSize = 16, fontStyle = 'Regular') {
  if (typeof chars === 'object' && chars !== null) {
    const opt = chars;
    chars = String(opt.text || opt.characters || '');
    x = opt.x !== undefined ? opt.x : 0;
    y = opt.y !== undefined ? opt.y : 0;
    w = opt.width || opt.w || 200;
    h = opt.height || opt.h || 20;
    fillHex = opt.color || opt.fillHex || '#0f172a';
    fontSize = opt.fontSize || 16;
    fontStyle = opt.fontWeight || opt.fontStyle || 'Regular';
  }
  if (fontStyle === 'normal') fontStyle = 'Regular';
  if (fontStyle === 'bold' || fontStyle === 'SemiBold' || fontStyle === 'semibold') fontStyle = 'Bold';
  if (fontStyle === 'medium') fontStyle = 'Medium';

  const t = figma.createText();
  try {
    t.fontName = { family: 'Inter', style: fontStyle };
  } catch (e) {
    t.fontName = { family: 'Inter', style: 'Regular' };
  }
  t.fontSize = fontSize;
  t.characters = String(chars || '');
  t.fills = [{ type: 'SOLID', color: hexToRgb(fillHex || '#0f172a') }];
  t.x = x; t.y = y;
  t.textAutoResize = 'HEIGHT';
  try { t.resize(w, h || 20); } catch (e) { }
  figma.currentPage.appendChild(t);
  return t;
}

function _eslMakeStroke(node, strokeHex, weight = 2) {
  node.strokes = [{ type: 'SOLID', color: hexToRgb(strokeHex) }];
  node.strokeWeight = weight;
}

function _eslGroup(nodes, name) {
  try {
    const g = figma.group(nodes, figma.currentPage);
    g.name = name;
    return g;
  } catch (e) { return null; }
}

function getNextBlockPosition(estW = 1600, estH = 1000) {
  if (typeof findSmartNonOverlappingPosition === "function") {
    return findSmartNonOverlappingPosition(estW, estH, "BOTTOM");
  }
  return { x: 0, y: 0 };
}

function _eslGetOrigin(estW = 1400, estH = 800, params = null) {
  let pos;
  if (params && params.replaceNodeId) {
    const oldNode = figma.getNodeById(params.replaceNodeId);
    if (oldNode && isNodeValidForCanvasBounds(oldNode)) {
      const orig = { x: Math.round(oldNode.x), y: Math.round(oldNode.y) };
      setTimeout(() => {
        try { oldNode.remove(); } catch (e) { }
      }, 50);
      return orig;
    }
  }
  if (params && typeof params.x === "number" && typeof params.y === "number") {
    pos = { x: Math.round(params.x), y: Math.round(params.y) };
  } else {
    pos = findSmartNonOverlappingPosition(estW, estH, 'RIGHT');
  }

  // Strict clamp: Coordinates must NEVER be outside realistic canvas dimensions
  if (pos.x < -40000 || pos.x > 400000 || pos.y < -40000 || pos.y > 400000 || isNaN(pos.x) || isNaN(pos.y)) {
    console.warn("Out-of-bounds coordinates detected:", pos, "resetting to viewport center");
    pos = getViewportCenter(estW, estH);
  }
  return pos;
}

function _eslScrollTo(nodes) {
  try {
    const grp = nodes.find(n => n && (n.type === 'GROUP' || n.type === 'SECTION')) || nodes[0];
    if (grp) {
      figma.currentPage.selection = [grp];
      if (figma.viewport && figma.viewport.center) {
        const vp = figma.viewport.center;
        const zoom = figma.viewport.zoom || 1;
        const dist = Math.hypot(grp.x + (grp.width || 0) / 2 - vp.x, grp.y + (grp.height || 0) / 2 - vp.y);
        // If distance on screen is large (> 1200px) or node is out of sight, scroll to it so teacher sees it
        if (dist * zoom > 1200 || dist > 3500) {
          figma.viewport.scrollAndZoomIntoView([grp]);
        }
      }
    }
  } catch (e) { }
}

function formatBlockTitleWithLevel(bloomTag, rawTitle, level) {
  let t = (rawTitle || '').trim();
  // Strip all duplicate level tags like (A0), [A0], (A1), [B2] etc. anywhere in title
  t = t.replace(/\s*[\(\[]\s*([A-C][0-2])\s*[\)\]]/gi, '').trim();
  const lvl = (level || 'A2').toUpperCase();
  return (bloomTag || '') + t + '   [' + lvl + ']';
}

// ─── drawESLQuizPhoto (Nordic Pastel Theme) ──────────────────────────────
async function drawESLQuizPhoto(params) {
  await _eslEnsureFonts();
  const { title, level, instruction, questions = [], hashtags = [], design = {} } = params;

  // Theme 1: Nordic Pastel
  const C = {
    bg_block: '#fafaf9', bg_card: '#ffffff', border: '#e5e7eb',
    accent: '#5eead4', header_bg: '#ffffff', correct: '#34d399',
    wrong: '#f87171', button_default: '#ffffff', text_primary: '#0f172a',
    text_secondary: '#334155', text_hashtags: '#64748b',
    ...(design.colors || {})
  };

  const hasImages = Boolean(
    params.has_images ||
    questions.some(q => (q.image_base64 && q.image_base64.length > 0) ||
      (q.image_url && typeof q.image_url === 'string' && q.image_url.startsWith('http')))
  );

  const nodes = [];
  const PAD = 32;
  const isTwoCol = questions.length > 1;
  const BLOCK_W = params.width || (isTwoCol ? 1680 : 1200);
  const COL_GAP = 28;
  const ROW_GAP = 24;
  const colW = isTwoCol ? Math.floor((BLOCK_W - PAD * 2 - COL_GAP) / 2) : (BLOCK_W - PAD * 2);

  const Q_IMG_W = hasImages ? (isTwoCol ? 260 : 340) : 0;
  const Q_IMG_H = hasImages ? (isTwoCol ? 240 : 260) : 0;
  const cardH = hasImages ? Math.max(Q_IMG_H + 40, 280) : 280;
  const imgFrameH = cardH - 40;

  const totalRows = isTwoCol ? Math.ceil(questions.length / 2) : questions.length;
  const estH = 200 + totalRows * (cardH + ROW_GAP) + 120;
  const origin = _eslGetOrigin(BLOCK_W, estH, params);
  const BX = origin.x; const BY = origin.y;
  const startGridY = BY + PAD + 64 + 14 + 48 + 24;

  // Header and Background will be drawn and resized at the end
  const bg = _eslMakeRect(BX, BY, BLOCK_W, 1000, C.bg_block, 24);
  bg.name = 'Block Container Background';
  bg.setPluginData('role', 'block_container');
  _eslMakeStroke(bg, C.border, 2.0);
  nodes.push(bg);

  const header = _eslMakeRect(BX + PAD, BY + PAD, BLOCK_W - PAD * 2, 64, C.header_bg, 16);
  _eslMakeStroke(header, C.accent, 2.0);
  nodes.push(header);

  const menuBtnW = 148;
  const menuBtnX = BX + BLOCK_W - PAD - menuBtnW - 10;
  const menuBtnY = BY + PAD + 12;
  const menuBtn = _eslMakeRect(menuBtnX, menuBtnY, menuBtnW, 40, C.menu_btn_bg || C.accent || '#5eead4', 20);
  menuBtn.setPluginData('role', 'back_to_menu');
  if (params.tocNodeId) {
    try { menuBtn.hyperlink = { type: 'NODE', value: params.tocNodeId }; } catch (e) { }
  }
  nodes.push(menuBtn);
  nodes.push(_eslMakeText('📑 В МЕНЮ ↩', menuBtnX + 8, menuBtnY + 11, menuBtnW - 16, 20, '#0f172a', 12, 'Bold'));

  const blockId = 'quiz_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);

  const resetBtnW = 168;
  const resetBtnX = menuBtnX - resetBtnW - 12;
  const resetBtnY = BY + PAD + 12;
  const resetBtn = _eslMakeRect(resetBtnX, resetBtnY, resetBtnW, 40, '#fca5a5', 20);
  resetBtn.setPluginData('role', 'reset_interactive');
  resetBtn.setPluginData('blockId', blockId);
  nodes.push(resetBtn);
  const resetTxt = _eslMakeText('🔄 СБРОСИТЬ ОТВЕТЫ', resetBtnX + 10, resetBtnY + 11, resetBtnW - 20, 20, '#0f172a', 12, 'Bold');
  resetTxt.setPluginData('role', 'reset_interactive');
  resetTxt.setPluginData('blockId', blockId);
  nodes.push(resetTxt);

  const titleAvailW = resetBtnX - (BX + PAD + 16) - 16;
  const bloomTag = (params.bloom_badge ? params.bloom_badge + '  •  ' : '');
  const titleTxt = _eslMakeText(
    formatBlockTitleWithLevel(bloomTag, title || 'Quiz', level),
    BX + PAD + 16, BY + PAD + 14, titleAvailW, 36, C.text_primary,
    (title && title.length > 35) ? 22 : 28, 'Bold'
  );
  titleTxt.name = 'Block Title'; titleTxt.setPluginData('role', 'block_title');
  nodes.push(titleTxt);

  const instrY = BY + PAD + 64 + 14;
  const instr = _eslMakeRect(BX + PAD, instrY, BLOCK_W - PAD * 2, 48, '#f8fafc', 12);
  nodes.push(instr);
  nodes.push(_eslMakeText('👉 ' + (instruction || 'Choose the correct answer!'), BX + PAD + 16, instrY + 12, BLOCK_W - PAD * 2 - 32, 28, '#1e293b', 16, 'Medium'));

  // Dynamic Grid Layout: Calculate required heights for each question and each row
  // Supports 3, 4, 5+ options and any question length without text overlap!
  const questionHeights = [];
  for (let i = 0; i < questions.length; i++) {
    const q = questions[i];
    const opts = q.options || [];
    const optCount = Math.max(opts.length, 2);
    const optBtnH = optCount >= 5 ? 34 : 38;
    const optGap = optCount >= 5 ? 6 : 8;
    const totalOptsH = optCount * optBtnH + (optCount - 1) * optGap;

    const qNum = String(i + 1) + '. ';
    const qFullStr = qNum + (q.sentence || q.question || '');
    const contentW = hasImages ? (colW - 20 - Q_IMG_W - 18 - 20) : (colW - 48);
    // Estimate text lines (Inter Bold 19px: ~10.8px per char in contentW)
    const charsPerLine = Math.max(15, Math.floor(contentW / 11));
    const estLines = Math.max(1, Math.ceil(qFullStr.length / charsPerLine));
    const estTextH = Math.max(34, estLines * 28);

    const neededH = 20 + estTextH + 14 + totalOptsH + 20;
    const minCardH = hasImages ? Math.max(Q_IMG_H + 40, 260) : 240;
    questionHeights.push({
      optCount,
      optBtnH,
      optGap,
      totalOptsH,
      estTextH,
      neededH: Math.max(neededH, minCardH)
    });
  }

  // Row heights = maximum needed height in that row
  const rowHeights = [];
  const rowStartY = [];
  let currentY = startGridY;
  for (let r = 0; r < totalRows; r++) {
    const idx0 = isTwoCol ? r * 2 : r;
    const idx1 = isTwoCol ? r * 2 + 1 : -1;
    const h0 = questionHeights[idx0] ? questionHeights[idx0].neededH : 280;
    const h1 = (idx1 >= 0 && questionHeights[idx1]) ? questionHeights[idx1].neededH : 0;
    const rH = Math.max(h0, h1);
    rowHeights.push(rH);
    rowStartY.push(currentY);
    currentY += rH + ROW_GAP;
  }

  // Questions Grid (Adaptive 2 Columns layout)
  for (let idx = 0; idx < questions.length; idx++) {
    const q = questions[idx];
    const col = isTwoCol ? (idx % 2) : 0;
    const row = isTwoCol ? Math.floor(idx / 2) : idx;
    const qX = BX + PAD + col * (colW + COL_GAP);
    const qY = rowStartY[row];
    const cardH = rowHeights[row];
    const qMeta = questionHeights[idx];

    // 1. Background Card is created FIRST and placed at the bottom of z-stack
    const qCard = _eslMakeRect(qX, qY, colW, cardH, C.bg_card, 20);
    _eslMakeStroke(qCard, C.border, 2.0);
    qCard.name = 'Question Card ' + (idx + 1);
    nodes.push(qCard);

    // 2. Image frame on the left side
    const imgFrameH = cardH - 40;
    if (hasImages) {
      const imgFrame = _eslMakeRect(qX + 20, qY + 20, Q_IMG_W, imgFrameH, '#f8fafc', 14);
      nodes.push(imgFrame);

      let imgLoaded = false;
      if (q.image_base64) {
        try {
          const bytes = base64ToUint8Array(q.image_base64);
          if (bytes) {
            const img = figma.createImage(bytes);
            imgFrame.fills = [{ type: 'IMAGE', imageHash: img.hash, scaleMode: 'FIT' }];
            imgLoaded = true;
          }
        } catch (e) { }
      } else if (q.image_url) {
        try {
          const resp = await fetch(q.image_url);
          const buf = await resp.arrayBuffer();
          const img = figma.createImage(new Uint8Array(buf));
          imgFrame.fills = [{ type: 'IMAGE', imageHash: img.hash, scaleMode: 'FIT' }];
          imgLoaded = true;
        } catch (e) { }
      }
      if (!imgLoaded) {
        nodes.push(_eslMakeText('📷', qX + 20 + Q_IMG_W / 2 - 20, qY + 20 + imgFrameH / 2 - 20, 40, 40, '#cbd5e1', 32, 'Regular'));
      }
    }

    // 3. Question Text on the right side
    const contentStartX = hasImages ? (qX + 20 + Q_IMG_W + 18) : (qX + 24);
    const contentW = hasImages ? (colW - 20 - Q_IMG_W - 18 - 20) : (colW - 48);

    const qNum = String(idx + 1) + '. ';
    const qFullStr = qNum + (q.sentence || q.question || '');

    const qTxt = _eslMakeText(qFullStr, contentStartX, qY + 20, contentW, qMeta.estTextH, C.text_primary, 19, 'Bold');
    qTxt.name = 'Question Text ' + (idx + 1);
    nodes.push(qTxt);

    // Measure actual rendered text height from Figma text node
    const actualTextH = Math.max(qTxt.height || 0, qMeta.estTextH, 32);

    // 4. Answer Buttons — Positioned strictly below question text with safe gap
    const opts = q.options || [];
    const optCount = opts.length || 3;
    const optBtnH = qMeta.optBtnH;
    const optGap = qMeta.optGap;
    const optStartY = qY + 20 + actualTextH + 14;

    for (let oi = 0; oi < optCount; oi++) {
      const btnY = optStartY + oi * (optBtnH + optGap);
      const isCorrect = oi === (q.correct_index || 0);

      const optCard = _eslMakeRect(contentStartX, btnY, contentW, optBtnH, C.button_default, 10);
      _eslMakeStroke(optCard, '#e2e8f0', 1.5);
      optCard.name = 'Option ' + oi;
      optCard.setPluginData('role', 'quiz_option');
      optCard.setPluginData('blockId', blockId);
      optCard.setPluginData('isCorrect', isCorrect ? 'true' : 'false');
      optCard.setPluginData('defaultFill', C.button_default);
      optCard.setPluginData('defaultStroke', '#e2e8f0');
      optCard.setPluginData('defaultStrokeWeight', '1.5');
      optCard.setPluginData('state', 'initial');
      nodes.push(optCard);

      // Clean button text without A) B) C) prefixes
      const optTxtY = btnY + Math.round((optBtnH - 20) / 2);
      const optTxt = _eslMakeText((opts[oi] || ''), contentStartX + 14, optTxtY, contentW - 28, 20, C.text_primary, 16, 'Medium');
      optTxt.name = 'Option Text';
      optTxt.setPluginData('role', 'quiz_option_text');
      optTxt.setPluginData('blockId', blockId);
      optTxt.setPluginData('isCorrect', isCorrect ? 'true' : 'false');
      nodes.push(optTxt);

      const optGrp = _eslGroup([optCard, optTxt], 'Option ' + oi);
      if (optGrp) {
        optGrp.setPluginData('role', 'quiz_option_container');
        optGrp.setPluginData('blockId', blockId);
        optGrp.setPluginData('isCorrect', isCorrect ? 'true' : 'false');
        nodes.push(optGrp);
      }
    }
  }

  // Hashtags footer
  const gridBottomY = (totalRows > 0 ? (rowStartY[totalRows - 1] + rowHeights[totalRows - 1]) : startGridY);
  const tagsY = gridBottomY + 24;
  const tagsNode = _eslMakeRect(BX + PAD, tagsY, BLOCK_W - PAD * 2, 38, '#f8fafc', 12);
  nodes.push(tagsNode);
  const tagsStr = (hashtags.length ? hashtags.join(' ') : '#quiz #english #esl');
  const tagsTxt = _eslMakeText(tagsStr, BX + PAD + 14, tagsY + 9, BLOCK_W - PAD * 2 - 28, 20, C.text_hashtags, 14, 'Regular');
  tagsTxt.name = 'Hashtags Footer';
  tagsTxt.setPluginData('role', 'hashtags_footer');
  nodes.push(tagsTxt);

  const finalTotalH = (tagsY + 38 + PAD) - BY;
  bg.resize(BLOCK_W, finalTotalH);

  const grp = _eslGroup(nodes, title || 'Quiz Block');
  if (grp) {
    grp.setPluginData('blockId', blockId);
    grp.setPluginData('role', 'esl_activity_block');
    grp.setPluginData('created_at', String(Date.now()));
  }
  _eslScrollTo(nodes);
  figma.notify('✅ Quiz photo created!', { timeout: 2500 });
  return { ok: true, success: true, nodeId: grp ? grp.id : (nodes[0] && nodes[0].id), x: Math.round(grp ? grp.x : BX), y: Math.round(grp ? grp.y : BY), width: Math.round(BLOCK_W), height: Math.round(finalTotalH) };
}

async function drawESLFlipCards(params) {
  await _eslEnsureFonts();
  const { title, level, instruction, cards = [], hashtags = [], design = {} } = params;

  // Theme 1: Nordic Pastel
  const C = {
    bg_block: '#fafaf9', bg_card: '#ffffff', border: '#e5e7eb',
    accent: '#5eead4', header_bg: '#ffffff', text_primary: '#0f172a',
    text_secondary: '#334155', text_hashtags: '#64748b',
    ...(design.colors || {})
  };
  const nodes = [];
  const CARD_W = 340; const CARD_H = 400; const CARD_GAP = 24;
  const COLS = 3; const PAD = 36;
  const ROWS = Math.ceil(cards.length / COLS);
  const BLOCK_W = COLS * (CARD_W + CARD_GAP) - CARD_GAP + PAD * 2;
  const BLOCK_H = 80 + 52 + 24 + ROWS * (CARD_H + CARD_GAP) + 64;
  const origin = _eslGetOrigin(BLOCK_W, BLOCK_H, params);
  const BX = origin.x; const BY = origin.y;

  // Background Container
  const bg = _eslMakeRect(BX, BY, BLOCK_W, BLOCK_H, C.bg_block, 24);
  bg.name = 'Block Container Background';
  bg.setPluginData('role', 'block_container');
  _eslMakeStroke(bg, C.border, 2.0);
  nodes.push(bg);

  // Header Banner
  const hdr = _eslMakeRect(BX + PAD, BY + PAD, BLOCK_W - PAD * 2, 64, C.header_bg, 16);
  _eslMakeStroke(hdr, C.accent, 2.0);
  nodes.push(hdr);

  // Back to menu btn (rightmost)
  const menuBtnW = 148;
  const menuBtnX = BX + BLOCK_W - PAD - menuBtnW - 10;
  const menuBtnY = BY + PAD + 12;
  const mBtn = _eslMakeRect(menuBtnX, menuBtnY, menuBtnW, 40, C.menu_btn_bg || C.accent || '#5eead4', 20);
  mBtn.setPluginData('role', 'back_to_menu');
  nodes.push(mBtn);
  nodes.push(_eslMakeText('📑 В МЕНЮ ↩', menuBtnX + 10, menuBtnY + 11, menuBtnW - 20, 20, '#0f172a', 12, 'Bold'));

  const blockId = 'flip_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);

  // Reset button: [🔄 ЗАКРЫТЬ ВСЕХ 🐱]
  const resetBtnW = 164;
  const resetBtnX = menuBtnX - resetBtnW - 12;
  const resetBtn = _eslMakeRect(resetBtnX, menuBtnY, resetBtnW, 40, '#fca5a5', 20);
  resetBtn.setPluginData('role', 'reset_cats');
  resetBtn.setPluginData('blockId', blockId);
  nodes.push(resetBtn);
  const resetTxt = _eslMakeText('🔄 ЗАКРЫТЬ ВСЕХ 🐱', resetBtnX + 10, menuBtnY + 11, resetBtnW - 20, 20, '#0f172a', 12, 'Bold');
  resetTxt.setPluginData('role', 'reset_cats');
  resetTxt.setPluginData('blockId', blockId);
  nodes.push(resetTxt);

  // Title Text
  const titleAvailW = resetBtnX - (BX + PAD + 20) - 16;
  const bloomTag = (params.bloom_badge ? params.bloom_badge + '  •  ' : '');
  const titleTxt = _eslMakeText(
    formatBlockTitleWithLevel(bloomTag, title || '🐱 Открывашки • Guess & Reveal!', level),
    BX + PAD + 20, BY + PAD + 14, titleAvailW, 32, C.text_primary,
    (title && title.length > 35) ? 20 : 24, 'Bold'
  );
  titleTxt.name = 'Block Title';
  titleTxt.setPluginData('role', 'block_title');
  nodes.push(titleTxt);

  // Instruction Banner
  const iY = BY + PAD + 76;
  const instr = _eslMakeRect(BX + PAD, iY, BLOCK_W - PAD * 2, 42, '#f8fafc', 12);
  nodes.push(instr);
  nodes.push(_eslMakeText('👉 ' + (instruction || 'Опишите персонажа на английском! Нажмите на карточку, чтобы открыть секретный вопрос!'), BX + PAD + 16, iY + 11, BLOCK_W - PAD * 2 - 32, 22, '#1e293b', 14, 'Medium'));

  // Multicolor energetic palette with high contrast dark text
  const CARD_PALETTES = [
    { bg: '#f0fdfa', stroke: '#14b8a6', text: '#0f766e' },
    { bg: '#eff6ff', stroke: '#3b82f6', text: '#1d4ed8' },
    { bg: '#f5f3ff', stroke: '#a855f7', text: '#6d28d9' },
    { bg: '#fff7ed', stroke: '#f97316', text: '#c2410c' },
    { bg: '#fdf4ff', stroke: '#d946ef', text: '#a21caf' },
    { bg: '#f0fdf4', stroke: '#34d399', text: '#047857' }
  ];

  // Cards grid
  const cardsStartY = iY + 42 + 24;
  for (let i = 0; i < cards.length; i++) {
    const card = cards[i];
    const col = i % COLS;
    const row = Math.floor(i / COLS);
    const cX = BX + PAD + col * (CARD_W + CARD_GAP);
    const cY = cardsStartY + row * (CARD_H + CARD_GAP);
    const palette = CARD_PALETTES[i % CARD_PALETTES.length];
    const cardId = 'cat_card_' + (card.id || (i + 1));

    // ─────────────────────────────────────────────────────────────────────────
    // LAYER 1 (UNDERNEATH): Secret Question Card (Back — Pure White Card)
    // ─────────────────────────────────────────────────────────────────────────
    const backNodes = [];
    const backBg = _eslMakeRect(cX, cY, CARD_W, CARD_H, '#ffffff', 24);
    _eslMakeStroke(backBg, palette.stroke, 2);
    backBg.name = 'Question Card Back';
    backBg.setPluginData('role', 'question_card');
    backBg.setPluginData('card_id', cardId);
    backNodes.push(backBg);

    // Top role pill on back
    const bHeader = _eslMakeRect(cX + 12, cY + 12, CARD_W - 24, 44, palette.bg, 16);
    bHeader.setPluginData('role', 'question_card');
    bHeader.setPluginData('card_id', cardId);
    backNodes.push(bHeader);

    const bHeaderTxt = _eslMakeText(
      `💬 ${(i + 1)}. ${String(card.label || card.role || 'QUESTION').toUpperCase()}`,
      cX + 16, cY + 22, CARD_W - 32, 24, palette.text, 16, 'Bold'
    );
    bHeaderTxt.setPluginData('role', 'question_card');
    bHeaderTxt.setPluginData('card_id', cardId);
    backNodes.push(bHeaderTxt);

    // Question body text (clean, comfortable margins, dark charcoal font)
    const qRaw = card.question || 'Speaking prompt';
    const qTxt = _eslMakeText(qRaw, cX + 24, cY + 76, CARD_W - 48, 200, '#0f172a', 22, 'Bold');
    qTxt.setPluginData('role', 'question_card');
    qTxt.setPluginData('card_id', cardId);
    backNodes.push(qTxt);

    // Bonus question or tip (if exists)
    if (card.bonus_question || card.follow_up) {
      const bonusTxt = _eslMakeText(
        '💡 ' + (card.bonus_question || card.follow_up),
        cX + 24, cY + 284, CARD_W - 48, 56, palette.text, 16, 'Medium'
      );
      bonusTxt.setPluginData('role', 'question_card');
      bonusTxt.setPluginData('card_id', cardId);
      backNodes.push(bonusTxt);
    }

    // Bottom close button pill: [ ↩ Нажмите, чтобы закрыть ]
    const closeBtnY = cY + CARD_H - 48;
    const closePill = _eslMakeRect(cX + 16, closeBtnY, CARD_W - 32, 36, '#f1f5f9', 16);
    closePill.setPluginData('role', 'question_card');
    closePill.setPluginData('card_id', cardId);
    backNodes.push(closePill);

    const closeTxt = _eslMakeText('↩ Нажмите, чтобы закрыть', cX + 20, closeBtnY + 8, CARD_W - 40, 20, '#64748b', 14, 'Medium');
    closeTxt.setPluginData('role', 'question_card');
    closeTxt.setPluginData('card_id', cardId);
    backNodes.push(closeTxt);

    // Push all back nodes into the main block list FIRST
    for (const bn of backNodes) nodes.push(bn);

    // ─────────────────────────────────────────────────────────────────────────
    // LAYER 2 (ON TOP): Interactive Front Cover (Character + Role Badge)
    // ─────────────────────────────────────────────────────────────────────────
    const frontNodes = [];

    // Front Card Background Rect (sits directly on top of backBg)
    const frontBg = _eslMakeRect(cX, cY, CARD_W, CARD_H, palette.bg, 24);
    _eslMakeStroke(frontBg, palette.stroke, 2.0);
    frontBg.name = 'Cat Cover #' + (i + 1);
    frontBg.setPluginData('role', 'cat_cover');
    frontBg.setPluginData('card_id', cardId);
    frontNodes.push(frontBg);

    // Top Role Pill
    const fHeader = _eslMakeRect(cX + 16, cY + 16, CARD_W - 32, 48, '#ffffff', 16);
    _eslMakeStroke(fHeader, palette.stroke, 1.5);
    fHeader.setPluginData('role', 'cat_cover');
    fHeader.setPluginData('card_id', cardId);
    frontNodes.push(fHeader);

    const fHeaderTxt = _eslMakeText(
      String(card.label || card.role || 'WORD').toUpperCase(),
      cX + 20, cY + 28, CARD_W - 40, 24, palette.text, 18, 'Bold'
    );
    fHeaderTxt.setPluginData('role', 'cat_cover');
    fHeaderTxt.setPluginData('card_id', cardId);
    frontNodes.push(fHeaderTxt);

    // Dedicated Character Area
    const imgY = cY + 76;
    const imgH = CARD_H - 76 - 64;
    const imgArea = _eslMakeRect(cX + 16, imgY, CARD_W - 32, imgH, '#ffffff', 16);
    imgArea.name = 'Character Image';
    imgArea.setPluginData('role', 'cat_cover');
    imgArea.setPluginData('card_id', cardId);
    frontNodes.push(imgArea);

    if (card.image_base64) {
      try {
        const bytes = base64ToUint8Array(card.image_base64);
        const img = figma.createImage(bytes);
        imgArea.fills = [{ type: 'IMAGE', imageHash: img.hash, scaleMode: 'FIT' }];
      } catch (e) { }
    } else if (card.image_url) {
      try {
        const resp = await fetch(card.image_url);
        const buf = await resp.arrayBuffer();
        const img = figma.createImage(new Uint8Array(buf));
        imgArea.fills = [{ type: 'IMAGE', imageHash: img.hash, scaleMode: 'FIT' }];
      } catch (e) { }
    } else {
      frontNodes.push(_eslMakeText('📷', cX + 16 + (CARD_W - 32) / 2 - 20, imgY + imgH / 2 - 20, 40, 40, '#cbd5e1', 32, 'Regular'));
    }

    // Bottom Action Pill
    const btnY = cY + CARD_H - 52;
    const btnPill = _eslMakeRect(cX + 16, btnY, CARD_W - 32, 40, '#ffffff', 16);
    _eslMakeStroke(btnPill, palette.stroke, 1.5);
    btnPill.setPluginData('role', 'cat_cover');
    btnPill.setPluginData('card_id', cardId);
    frontNodes.push(btnPill);

    const btnTxt = _eslMakeText('🐾 НАЖМИ, ЧТОБЫ ОТКРЫТЬ ➔', cX + 20, btnY + 11, CARD_W - 40, 20, palette.text, 14, 'Bold');
    btnTxt.setPluginData('role', 'cat_cover');
    btnTxt.setPluginData('card_id', cardId);
    frontNodes.push(btnTxt);

    // Group the front cover elements so clicking anywhere on the cover toggles it!
    const coverGroup = _eslGroup(frontNodes, '🐱 Cat Cover #' + (i + 1));
    if (coverGroup) {
      coverGroup.setPluginData('role', 'cat_cover');
      coverGroup.setPluginData('card_id', cardId);
      coverGroup.setPluginData('blockId', blockId);
      nodes.push(coverGroup);
    } else {
      for (const fn of frontNodes) nodes.push(fn);
    }
  }

  // Hashtags footer
  const tY = BY + BLOCK_H - 48;
  const tBg = _eslMakeRect(BX + PAD, tY, BLOCK_W - PAD * 2, 38, '#f8fafc', 12);
  nodes.push(tBg);
  const tagsTxt = _eslMakeText((hashtags.join(' ') || '#открывашки #котики #speaking #разминка #english #interactive #game'), BX + PAD + 14, tY + 10, BLOCK_W - PAD * 2 - 28, 20, C.text_hashtags, 14);
  tagsTxt.name = 'Hashtags Footer';
  tagsTxt.setPluginData('role', 'hashtags_footer');
  nodes.push(tagsTxt);

  const grp = _eslGroup(nodes, title || 'Flip Cards Block');
  if (grp) {
    grp.setPluginData('blockId', blockId);
    grp.setPluginData('role', 'esl_activity_block');
    grp.setPluginData('created_at', String(Date.now()));
  }
  _eslScrollTo(nodes);
  figma.notify('✅ Интерактивные открывашки созданы!', { timeout: 2500 });
  return { ok: true, success: true, nodeId: grp ? grp.id : (nodes[0] && nodes[0].id), x: Math.round(grp ? grp.x : BX), y: Math.round(grp ? grp.y : BY), width: Math.round(BLOCK_W), height: Math.round(BLOCK_H) };
}

// ─── drawESLVideoQuiz (Nordic Pastel Theme) ──────────────────────────────────────────────────────
async function drawESLVideoQuiz(params) {
  await _eslEnsureFonts();
  const { title, level, instruction, youtube_url, vocabulary = [], questions = [], hashtags = [], design = {} } = params;

  // Theme 1: Nordic Pastel
  const C = {
    bg_block: '#fafaf9', bg_card: '#ffffff', border: '#e5e7eb',
    accent: '#5eead4', header_bg: '#ffffff', text_primary: '#0f172a',
    text_secondary: '#334155', text_hashtags: '#64748b',
    ...(design.colors || {})
  };
  const nodes = [];
  const PAD = 32; const BLOCK_W = 1500;
  const VOC_W = 500; const Q_W = BLOCK_W - VOC_W - PAD * 3;
  const ROW_H = 64; const Q_H = 140;
  const BLOCK_H = 80 + 52 + 20 + 220 + 20 + Math.max(vocabulary.length * (ROW_H + 12), questions.length * (Q_H + 24)) + 80;
  const origin = _eslGetOrigin(BLOCK_W, BLOCK_H, params);
  const BX = origin.x; const BY = origin.y;

  // Background
  const bg = _eslMakeRect(BX, BY, BLOCK_W, BLOCK_H, C.bg_block, 24);
  bg.name = 'Block Container Background'; bg.setPluginData('role', 'block_container');
  _eslMakeStroke(bg, C.border, 2.0); nodes.push(bg);

  // Header
  const hdr = _eslMakeRect(BX + PAD, BY + PAD, BLOCK_W - PAD * 2, 64, C.header_bg, 16);
  _eslMakeStroke(hdr, C.accent, 2.0); nodes.push(hdr);

  // Back to menu btn (rightmost)
  const menuBtnW = 148;
  const menuBtnX = BX + BLOCK_W - PAD - menuBtnW - 10;
  const menuBtnY = BY + PAD + 12;
  const mBtn = _eslMakeRect(menuBtnX, menuBtnY, menuBtnW, 40, C.menu_btn_bg || C.accent || '#5eead4', 20);
  mBtn.setPluginData('role', 'back_to_menu');
  nodes.push(mBtn);
  nodes.push(_eslMakeText('📑 В МЕНЮ ↩', menuBtnX + 10, menuBtnY + 11, menuBtnW - 20, 20, '#0f172a', 12, 'Bold'));

  // Reset button: [🔄 СБРОСИТЬ ОТВЕТЫ]
  const resetBtnW = 168;
  const resetBtnX = menuBtnX - resetBtnW - 12;
  const resetBtn = _eslMakeRect(resetBtnX, menuBtnY, resetBtnW, 40, '#fca5a5', 20);
  resetBtn.setPluginData('role', 'reset_interactive');
  nodes.push(resetBtn);
  nodes.push(_eslMakeText('🔄 СБРОСИТЬ ОТВЕТЫ', resetBtnX + 10, menuBtnY + 11, resetBtnW - 20, 20, '#0f172a', 12, 'Bold'));

  const titleAvailW = resetBtnX - (BX + PAD + 16) - 16;
  const titleTxt = _eslMakeText(
    formatBlockTitleWithLevel('', title || 'Video Quiz', level || 'B1'),
    BX + PAD + 16, BY + PAD + 14, titleAvailW, 32, C.text_primary,
    (title && title.length > 35) ? 20 : 24, 'Bold'
  );
  titleTxt.name = 'Block Title';
  titleTxt.setPluginData('role', 'block_title');
  nodes.push(titleTxt);

  // Instruction
  const iY = BY + PAD + 72;
  const instr = _eslMakeRect(BX + PAD, iY, BLOCK_W - PAD * 2, 42, '#f8fafc', 12);
  nodes.push(instr);
  nodes.push(_eslMakeText('👉 ' + (instruction || 'Watch the video and answer the questions!'), BX + PAD + 14, iY + 11, BLOCK_W - PAD * 2 - 28, 22, '#1e293b', 14, 'Medium'));

  // YouTube embed placeholder
  const vidY = iY + 52;
  const vidCard = _eslMakeRect(BX + PAD, vidY, BLOCK_W - PAD * 2, 200, '#ffffff', 16);
  _eslMakeStroke(vidCard, '#ef4444', 2); nodes.push(vidCard);
  nodes.push(_eslMakeText('▶️  ' + (youtube_url || 'YouTube Video'), BX + PAD + 16, vidY + 86, BLOCK_W - PAD * 2 - 32, 28, '#dc2626', 18, 'Bold'));

  const contentY = vidY + 220;

  // Left: Vocabulary table
  const vocX = BX + PAD;
  const vocHdr = _eslMakeRect(vocX, contentY, VOC_W, 48, '#ecfdf5', 12);
  _eslMakeStroke(vocHdr, '#a7f3d0', 1.5); nodes.push(vocHdr);
  nodes.push(_eslMakeText('📚 KEY VOCABULARY', vocX + 14, contentY + 12, VOC_W - 28, 24, '#065f46', 16, 'Bold'));

  for (let i = 0; i < vocabulary.length; i++) {
    const voc = vocabulary[i];
    const vy = contentY + 60 + i * (ROW_H + 12);
    const rowBg = i % 2 === 0 ? '#ffffff' : '#f8fafc';
    const rowRect = _eslMakeRect(vocX, vy, VOC_W, ROW_H, rowBg, 12);
    _eslMakeStroke(rowRect, '#e2e8f0', 1.5); nodes.push(rowRect);
    nodes.push(_eslMakeText(voc.word || '', vocX + 12, vy + 12, 140, 40, '#0f172a', 18, 'Bold'));
    nodes.push(_eslMakeText(voc.transcription || '', vocX + 160, vy + 12, 120, 40, '#6366f1', 14, 'Medium'));
    nodes.push(_eslMakeText(voc.translation || '', vocX + 290, vy + 12, VOC_W - 302, 40, '#334155', 16, 'Medium'));
  }

  // Right: Questions
  const qX = BX + PAD + VOC_W + PAD;
  const qHdr = _eslMakeRect(qX, contentY, Q_W, 48, '#eff6ff', 12);
  _eslMakeStroke(qHdr, '#bfdbfe', 1.5); nodes.push(qHdr);
  nodes.push(_eslMakeText('❓ COMPREHENSION QUESTIONS', qX + 14, contentY + 12, Q_W - 28, 24, '#1e40af', 16, 'Bold'));

  for (let i = 0; i < questions.length; i++) {
    const q = questions[i];
    const qy = contentY + 60 + i * (Q_H + 24);
    const qCard = _eslMakeRect(qX, qy, Q_W, Q_H, '#ffffff', 16);
    _eslMakeStroke(qCard, C.border, 2.0); nodes.push(qCard);

    // Question Text
    nodes.push(_eslMakeText((q.emoji || '') + ' ' + (q.question || ''), qX + 16, qy + 16, Q_W - 32, 40, '#0f172a', 18, 'Bold'));

    // Interactive Options (No LBLS, Just Text)
    const opts = q.options || [];
    const optCount = Math.max(opts.length, 2);
    const oGap = 12;
    const oW = Math.floor((Q_W - 32 - (optCount - 1) * oGap) / optCount);
    for (let oi = 0; oi < optCount; oi++) {
      const oX = qX + 16 + oi * (oW + oGap);
      const isCorrect = oi === (q.correct_index || 0);

      const oCard = _eslMakeRect(oX, qy + 64, oW, 56, '#ffffff', 12);
      _eslMakeStroke(oCard, '#e2e8f0', 2.0);
      oCard.name = 'Option ' + oi;
      oCard.setPluginData('role', 'quiz_option');
      oCard.setPluginData('isCorrect', isCorrect ? 'true' : 'false');
      oCard.setPluginData('defaultFill', '#ffffff');
      oCard.setPluginData('defaultStroke', '#e2e8f0');
      oCard.setPluginData('defaultStrokeWeight', '2.0');
      oCard.setPluginData('state', 'initial');
      nodes.push(oCard);

      const optTxt = _eslMakeText((opts[oi] || ''), oX + 12, qy + 78, oW - 24, 28, '#0f172a', 16, 'Medium');
      optTxt.textAlignHorizontal = 'CENTER';
      optTxt.setPluginData('role', 'quiz_option_text');
      optTxt.setPluginData('isCorrect', isCorrect ? 'true' : 'false');
      nodes.push(optTxt);

      const optGrp = _eslGroup([oCard, optTxt], 'Option ' + oi);
      if (optGrp) {
        optGrp.setPluginData('role', 'quiz_option_container');
        optGrp.setPluginData('isCorrect', isCorrect ? 'true' : 'false');
        nodes.push(optGrp);
      }
    }
  }

  // Final resize based on actual content
  const maxContentH = Math.max(
    60 + vocabulary.length * (ROW_H + 12),
    60 + questions.length * (Q_H + 24)
  );
  const finalTotalH = (contentY + maxContentH) - BY + 60;
  bg.resize(BLOCK_W, finalTotalH);

  // Hashtags
  const tY = BY + finalTotalH - 48;
  const tBg = _eslMakeRect(BX + PAD, tY, BLOCK_W - PAD * 2, 38, '#f8fafc', 12);
  nodes.push(tBg);
  const tagsTxt = _eslMakeText((hashtags.join(' ') || '#video #english #quiz'), BX + PAD + 14, tY + 9, BLOCK_W - PAD * 2 - 28, 20, C.text_hashtags, 14);
  tagsTxt.name = 'Hashtags Footer';
  tagsTxt.setPluginData('role', 'hashtags_footer');
  nodes.push(tagsTxt);

  const grp = _eslGroup(nodes, title || 'Video Quiz Block');
  if (grp) {
    grp.setPluginData('role', 'esl_activity_block');
    grp.setPluginData('created_at', String(Date.now()));
  }
  _eslScrollTo(nodes);
  figma.notify('✅ Video quiz block created!', { timeout: 2500 });
  return { ok: true, success: true, nodeId: grp ? grp.id : (nodes[0] && nodes[0].id), x: Math.round(grp ? grp.x : BX), y: Math.round(grp ? grp.y : BY), width: Math.round(BLOCK_W), height: Math.round(BLOCK_H) };
}

// ─── drawESLVocabularyTable (Light Worksheet Theme) ────────────────────────
async function drawESLVocabularyTable(params) {
  await _eslEnsureFonts();
  const { title, level, instruction, columns = [], rows = [], hashtags = [], design = {} } = params;

  // Theme 1: Nordic Pastel
  const C = {
    bg_block: '#fafaf9', bg_card: '#ffffff', border: '#e5e7eb',
    accent: '#5eead4', header_bg: '#ffffff', text_primary: '#0f172a',
    text_secondary: '#334155', text_hashtags: '#64748b',
    ...(design.colors || {})
  };
  const nodes = [];
  const PAD = 32;
  const HAS_IMAGES = rows.some(r => r.image_base64 && r.image_base64.length > 0);
  const IMG_COL_W = HAS_IMAGES ? 130 : 0;
  const ROW_H = HAS_IMAGES ? 110 : 64;
  const HEADER_ROW_H = 50;
  // Column widths: [word, translation, type, example]
  const DATA_COL_WIDTHS = HAS_IMAGES ? [220, 180, 160, 440] : [260, 200, 180, 460];
  const TOTAL_DATA_W = DATA_COL_WIDTHS.reduce((a, b) => a + b, 0);
  const BASE_W = IMG_COL_W + TOTAL_DATA_W + PAD * 2 + (HAS_IMAGES ? 8 : 12);
  const BLOCK_W = params.width || BASE_W;
  if (params.width && params.width > BASE_W) {
    DATA_COL_WIDTHS[DATA_COL_WIDTHS.length - 1] += (params.width - BASE_W);
  }
  const BLOCK_H = 80 + 52 + 20 + HEADER_ROW_H + rows.length * (ROW_H + 4) + 60;
  const origin = _eslGetOrigin(BLOCK_W, BLOCK_H, params);
  const BX = origin.x; const BY = origin.y;

  // Background
  const bg = _eslMakeRect(BX, BY, BLOCK_W, BLOCK_H, C.bg_block, 24);
  bg.name = 'Block Container Background'; bg.setPluginData('role', 'block_container');
  _eslMakeStroke(bg, C.border, 2.0); nodes.push(bg);

  // Header
  const hdr = _eslMakeRect(BX + PAD, BY + PAD, BLOCK_W - PAD * 2, 64, C.header_bg, 16);
  _eslMakeStroke(hdr, C.accent, 2.0); nodes.push(hdr);
  const menuBtnW = 148;
  const menuBtnX = BX + BLOCK_W - PAD - menuBtnW - 10;
  const menuBtnY = BY + PAD + 12;
  const mBtn = _eslMakeRect(menuBtnX, menuBtnY, menuBtnW, 40, C.menu_btn_bg || C.accent || '#5eead4', 20);
  mBtn.setPluginData('role', 'back_to_menu');
  nodes.push(mBtn);
  nodes.push(_eslMakeText('📑 В МЕНЮ ↩', menuBtnX + 8, menuBtnY + 11, menuBtnW - 16, 20, '#0f172a', 12, 'Bold'));

  const titleAvailW = menuBtnX - (BX + PAD + 16) - 16;
  const bloomTag = (params.bloom_badge ? params.bloom_badge + '  •  ' : '');
  const titleTxt = _eslMakeText(
    formatBlockTitleWithLevel(bloomTag, title || 'Vocabulary', level),
    BX + PAD + 16, BY + PAD + 16, titleAvailW, 32, C.text_primary,
    (title && title.length > 35) ? 20 : 22, 'Bold'
  );
  titleTxt.name = 'Block Title'; titleTxt.setPluginData('role', 'block_title'); nodes.push(titleTxt);

  const iY = BY + PAD + 76;
  const instr = _eslMakeRect(BX + PAD, iY, BLOCK_W - PAD * 2, 42, '#f8fafc', 12);
  nodes.push(instr);
  nodes.push(_eslMakeText('👉 ' + (instruction || 'Study the vocabulary table.'), BX + PAD + 14, iY + 11, BLOCK_W - PAD * 2 - 28, 22, '#1e293b', 14, 'Medium'));

  // Table headers
  const tableY = iY + 52;
  let colLabels = (columns && columns.length > 0) ? [...columns] : (HAS_IMAGES
    ? ['Картинка', '№ / Слово (Word)', 'Перевод (Russian)', 'Тип / Роль (Role)', 'Пример в речи (Example Sentence)']
    : ['№ / Слово (Word)', 'Перевод (Russian)', 'Тип / Роль (Role)', 'Пример в речи (Example Sentence)']);

  if (!HAS_IMAGES) {
    colLabels = colLabels.filter(c => !c.toLowerCase().includes('картинк') && !c.toLowerCase().includes('image') && !c.toLowerCase().includes('photo'));
  }

  let cx = BX + PAD;

  // Image column header
  if (HAS_IMAGES) {
    const ch = _eslMakeRect(cx, tableY, IMG_COL_W - 4, HEADER_ROW_H, '#ffffff', 12);
    _eslMakeStroke(ch, '#e5e7eb', 1.5); nodes.push(ch);
    nodes.push(_eslMakeText(colLabels[0] || 'Картинка', cx + 8, tableY + 14, IMG_COL_W - 20, 24, C.text_primary, 14, 'Bold'));
    cx += IMG_COL_W;
  }
  // Data column headers
  for (let ci = 0; ci < DATA_COL_WIDTHS.length; ci++) {
    const labelIdx = HAS_IMAGES ? ci + 1 : ci;
    const ch = _eslMakeRect(cx, tableY, DATA_COL_WIDTHS[ci] - 4, HEADER_ROW_H, '#ffffff', 12);
    _eslMakeStroke(ch, '#e5e7eb', 1.5); nodes.push(ch);
    nodes.push(_eslMakeText(colLabels[labelIdx] || '', cx + 8, tableY + 14, DATA_COL_WIDTHS[ci] - 20, 24, C.text_primary, 14, 'Bold'));
    cx += DATA_COL_WIDTHS[ci];
  }

  // Table rows
  for (let ri = 0; ri < rows.length; ri++) {
    const row = rows[ri];
    const ry = tableY + HEADER_ROW_H + 4 + ri * (ROW_H + 4);
    const rowBg = '#ffffff';
    cx = BX + PAD;

    // Image cell
    if (HAS_IMAGES) {
      const imgCell = _eslMakeRect(cx, ry, IMG_COL_W - 4, ROW_H, '#f8fafc', 12);
      _eslMakeStroke(imgCell, '#e2e8f0', 1); nodes.push(imgCell);

      if (row.image_base64) {
        try {
          const bytes = base64ToUint8Array(row.image_base64);
          if (bytes) {
            const img = figma.createImage(bytes);
            imgCell.fills = [{ type: 'IMAGE', imageHash: img.hash, scaleMode: 'FIT' }];
          }
        } catch (e) {
          nodes.push(_eslMakeText('📷', cx + IMG_COL_W / 2 - 14, ry + ROW_H / 2 - 16, 28, 28, '#64748b', 22, 'Regular'));
        }
      } else {
        nodes.push(_eslMakeText('📷', cx + IMG_COL_W / 2 - 14, ry + ROW_H / 2 - 16, 28, 28, '#94a3b8', 22, 'Regular'));
      }
      cx += IMG_COL_W;
    }

    // Data cells
    const rowValues = [row.word || '', row.translation || '', row.type || '', row.example || ''];
    for (let ci = 0; ci < DATA_COL_WIDTHS.length; ci++) {
      const cell = _eslMakeRect(cx, ry, DATA_COL_WIDTHS[ci] - 4, ROW_H, rowBg, 8);
      _eslMakeStroke(cell, '#e5e7eb', 1.5); nodes.push(cell);

      const textColor = ci === 0 ? '#0f172a' : ci === 1 ? '#0f172a' : ci === 2 ? '#2563eb' : '#334155';
      const txtY = HAS_IMAGES ? ry + ROW_H / 2 - 18 : ry + 16;

      // Increased Font Sizes (English Word gets 22 instead of 14, others 16 instead of 12)
      const fontSize = ci === 0 ? 22 : 16;

      const txtNode = _eslMakeText(rowValues[ci], cx + 12, txtY, DATA_COL_WIDTHS[ci] - 24, HAS_IMAGES ? ROW_H - 12 : 36, textColor, fontSize, ci === 0 ? 'Bold' : 'Medium');
      if (HAS_IMAGES) txtNode.textAutoResize = 'HEIGHT';
      nodes.push(txtNode);
      cx += DATA_COL_WIDTHS[ci];
    }
  }

  // Hashtags
  const tY = BY + BLOCK_H - 46;
  const tBg = _eslMakeRect(BX + PAD, tY, BLOCK_W - PAD * 2, 36, '#f1f5f9', 8);
  _eslMakeStroke(tBg, '#e2e8f0', 1); nodes.push(tBg);
  const tagsTxt = _eslMakeText((hashtags.join(' ') || '#vocabulary #english #words'), BX + PAD + 12, tY + 8, BLOCK_W - PAD * 2 - 24, 20, C.text_hashtags, 12);
  tagsTxt.name = 'Hashtags Footer'; tagsTxt.setPluginData('role', 'hashtags_footer'); nodes.push(tagsTxt);

  const grp = _eslGroup(nodes, title || 'Vocabulary Table Block');
  if (grp) { grp.setPluginData('role', 'esl_activity_block'); grp.setPluginData('created_at', String(Date.now())); }
  _eslScrollTo(nodes);
  figma.notify('✅ Vocabulary table created!', { timeout: 2500 });
  return { ok: true, success: true, nodeId: grp ? grp.id : (nodes[0] && nodes[0].id), x: Math.round(grp ? grp.x : BX), y: Math.round(grp ? grp.y : BY), width: Math.round(BLOCK_W), height: Math.round(BLOCK_H) };
}

// ─── drawESLFlashcards (Nordic Pastel Theme) ─────────────────────────────
async function drawESLFlashcards(params) {
  await _eslEnsureFonts();
  const { title, level, instruction, cards = [], hashtags = [], design = {} } = params;

  const C = {
    bg_block: '#fafaf9', bg_card: '#ffffff', border: '#e5e7eb',
    accent: '#5eead4', header_bg: '#ffffff', text_primary: '#0f172a',
    text_secondary: '#334155', text_hashtags: '#64748b',
    ...(design.colors || {})
  };
  const nodes = [];
  const PAD = 32; const CARD_W = 340; const CARD_H = 260; const CARD_GAP = 28; const COLS = 3;
  const ROWS = Math.ceil(cards.length / COLS);
  const BLOCK_W = COLS * (CARD_W + CARD_GAP) - CARD_GAP + PAD * 2;
  const BLOCK_H = 80 + 52 + 20 + ROWS * (CARD_H + CARD_GAP) + 64;
  const origin = _eslGetOrigin(BLOCK_W, BLOCK_H, params);
  const BX = origin.x; const BY = origin.y;

  const bg = _eslMakeRect(BX, BY, BLOCK_W, BLOCK_H, C.bg_block, 24);
  bg.name = 'Block Container Background'; bg.setPluginData('role', 'block_container');
  _eslMakeStroke(bg, C.border, 2.0); nodes.push(bg);

  const hdr = _eslMakeRect(BX + PAD, BY + PAD, BLOCK_W - PAD * 2, 64, C.header_bg, 16);
  _eslMakeStroke(hdr, C.accent, 2.0); nodes.push(hdr);

  // Back to menu btn (rightmost)
  const menuBtnW = 148;
  const menuBtnX = BX + BLOCK_W - PAD - menuBtnW - 10;
  const menuBtnY = BY + PAD + 12;
  const mBtn = _eslMakeRect(menuBtnX, menuBtnY, menuBtnW, 40, C.menu_btn_bg || C.accent || '#5eead4', 20);
  mBtn.setPluginData('role', 'back_to_menu');
  nodes.push(mBtn);
  nodes.push(_eslMakeText('📑 В МЕНЮ ↩', menuBtnX + 10, menuBtnY + 11, menuBtnW - 20, 20, '#0f172a', 12, 'Bold'));

  // Reset button: [🔄 ЗАКРЫТЬ ВСЕХ]
  const resetBtnW = 164;
  const resetBtnX = menuBtnX - resetBtnW - 12;
  const resetBtn = _eslMakeRect(resetBtnX, menuBtnY, resetBtnW, 40, '#fca5a5', 20);
  resetBtn.setPluginData('role', 'reset_cats'); // Reuse the same logic to restore visibility of covers
  nodes.push(resetBtn);
  nodes.push(_eslMakeText('🔄 ЗАКРЫТЬ ВСЕХ', resetBtnX + 10, menuBtnY + 11, resetBtnW - 20, 20, '#0f172a', 12, 'Bold'));

  const titleAvailW = resetBtnX - (BX + PAD + 16) - 16;
  const titleTxt = _eslMakeText(
    formatBlockTitleWithLevel('', title || 'Flashcards', level || 'A2'),
    BX + PAD + 16, BY + PAD + 14, titleAvailW, 32, C.text_primary,
    (title && title.length > 35) ? 20 : 24, 'Bold'
  );
  titleTxt.name = 'Block Title';
  titleTxt.setPluginData('role', 'block_title');
  nodes.push(titleTxt);

  const iY = BY + PAD + 72;
  const instr = _eslMakeRect(BX + PAD, iY, BLOCK_W - PAD * 2, 42, '#f8fafc', 12);
  nodes.push(instr);
  nodes.push(_eslMakeText('👉 ' + (instruction || 'Click on a flashcard to reveal the answer!'), BX + PAD + 14, iY + 11, BLOCK_W - PAD * 2 - 28, 22, '#1e293b', 14, 'Medium'));

  const cardsStartY = iY + 42 + 24;

  const CARD_PALETTES = [
    { bg: '#f0fdfa', stroke: '#14b8a6', text: '#0f766e' },
    { bg: '#eff6ff', stroke: '#3b82f6', text: '#1d4ed8' },
    { bg: '#f5f3ff', stroke: '#a855f7', text: '#6d28d9' },
    { bg: '#fff7ed', stroke: '#f97316', text: '#c2410c' },
    { bg: '#fdf4ff', stroke: '#d946ef', text: '#a21caf' },
    { bg: '#f0fdf4', stroke: '#34d399', text: '#047857' }
  ];

  for (let i = 0; i < cards.length; i++) {
    const card = cards[i];
    const col = i % COLS; const row = Math.floor(i / COLS);
    const cX = BX + PAD + col * (CARD_W + CARD_GAP);
    const cY = cardsStartY + row * (CARD_H + CARD_GAP);
    const palette = CARD_PALETTES[i % CARD_PALETTES.length];
    const cardId = 'flashcard_' + (card.id || (i + 1));

    // ==========================================
    // LAYER 1 (BOTTOM): Answer (Back)
    // ==========================================
    const backNodes = [];
    const backBg = _eslMakeRect(cX, cY, CARD_W, CARD_H, '#ffffff', 24);
    _eslMakeStroke(backBg, palette.stroke, 2);
    backBg.name = 'Flashcard Answer';
    backBg.setPluginData('role', 'question_card');
    backBg.setPluginData('card_id', cardId);
    backNodes.push(backBg);

    // Answer Top Banner (shows the word again but smaller, or just "ANSWER")
    const bHeader = _eslMakeRect(cX + 12, cY + 12, CARD_W - 24, 44, palette.bg, 16);
    bHeader.setPluginData('role', 'question_card');
    bHeader.setPluginData('card_id', cardId);
    backNodes.push(bHeader);

    const bHeaderTxt = _eslMakeText(
      '🎯 ANSWER',
      cX + 16, cY + 22, CARD_W - 32, 24, palette.text, 16, 'Bold'
    );
    bHeaderTxt.setPluginData('role', 'question_card');
    bHeaderTxt.setPluginData('card_id', cardId);
    backNodes.push(bHeaderTxt);

    // Bottom: translation + example
    const backTxt = _eslMakeText(card.back || '', cX + 24, cY + 76, CARD_W - 48, 60, '#0f172a', 22, 'Bold');
    backTxt.setPluginData('role', 'question_card');
    backTxt.setPluginData('card_id', cardId);
    backNodes.push(backTxt);

    const exTxt = _eslMakeText(card.example || '', cX + 24, cY + 130, CARD_W - 48, 80, '#334155', 16, 'Medium');
    exTxt.setPluginData('role', 'question_card');
    exTxt.setPluginData('card_id', cardId);
    backNodes.push(exTxt);

    // Bottom close button pill: [ ↩ Нажмите, чтобы закрыть ]
    const closeBtnY = cY + CARD_H - 44;
    const closePill = _eslMakeRect(cX + 16, closeBtnY, CARD_W - 32, 32, '#f1f5f9', 10);
    closePill.setPluginData('role', 'question_card');
    closePill.setPluginData('card_id', cardId);
    backNodes.push(closePill);

    const closeTxt = _eslMakeText('↩ Нажмите, чтобы закрыть', cX + 20, closeBtnY + 8, CARD_W - 40, 18, '#64748b', 12, 'Medium');
    closeTxt.setPluginData('role', 'question_card');
    closeTxt.setPluginData('card_id', cardId);
    backNodes.push(closeTxt);

    for (const bn of backNodes) nodes.push(bn);

    // ==========================================
    // LAYER 2 (TOP): Question (Front Cover)
    // ==========================================
    const frontNodes = [];
    const frontBg = _eslMakeRect(cX, cY, CARD_W, CARD_H, palette.bg, 24);
    _eslMakeStroke(frontBg, palette.stroke, 2.0);
    frontBg.name = 'Flashcard Cover #' + (i + 1);
    frontBg.setPluginData('role', 'cat_cover'); // Reuse toggling logic
    frontBg.setPluginData('card_id', cardId);
    frontNodes.push(frontBg);

    // Front: English word + transcription
    const fWordTxt = _eslMakeText(card.front || '', cX + 24, cY + Math.floor(CARD_H / 2) - 40, CARD_W - 48, 50, palette.text, 28, 'Bold');
    fWordTxt.textAlignHorizontal = 'CENTER';
    fWordTxt.setPluginData('role', 'cat_cover');
    fWordTxt.setPluginData('card_id', cardId);
    frontNodes.push(fWordTxt);

    const fTransTxt = _eslMakeText(card.transcription || '', cX + 24, cY + Math.floor(CARD_H / 2) + 10, CARD_W - 48, 30, '#475569', 18, 'Medium');
    fTransTxt.textAlignHorizontal = 'CENTER';
    fTransTxt.setPluginData('role', 'cat_cover');
    fTransTxt.setPluginData('card_id', cardId);
    frontNodes.push(fTransTxt);

    // Bottom Action Pill
    const fBtnY = cY + CARD_H - 48;
    const fBtnPill = _eslMakeRect(cX + 16, fBtnY, CARD_W - 32, 36, '#ffffff', 12);
    _eslMakeStroke(fBtnPill, palette.stroke, 1.5);
    fBtnPill.setPluginData('role', 'cat_cover');
    fBtnPill.setPluginData('card_id', cardId);
    frontNodes.push(fBtnPill);

    const fBtnTxt = _eslMakeText('🐾 НАЖМИ, ЧТОБЫ ОТКРЫТЬ ➔', cX + 20, fBtnY + 9, CARD_W - 40, 20, palette.text, 13, 'Bold');
    fBtnTxt.textAlignHorizontal = 'CENTER';
    fBtnTxt.setPluginData('role', 'cat_cover');
    fBtnTxt.setPluginData('card_id', cardId);
    frontNodes.push(fBtnTxt);

    const coverGroup = _eslGroup(frontNodes, 'Flashcard Cover #' + (i + 1));
    if (coverGroup) {
      coverGroup.setPluginData('role', 'cat_cover');
      coverGroup.setPluginData('card_id', cardId);
      nodes.push(coverGroup);
    } else {
      for (const fn of frontNodes) nodes.push(fn);
    }
  }

  const tY = BY + BLOCK_H - 46;
  const tBg = _eslMakeRect(BX + PAD, tY, BLOCK_W - PAD * 2, 36, '#f8fafc', 12);
  nodes.push(tBg);
  const tagsTxt = _eslMakeText((hashtags.join(' ') || '#flashcards #english #vocabulary'), BX + PAD + 12, tY + 8, BLOCK_W - PAD * 2 - 24, 20, C.text_hashtags, 14);
  tagsTxt.name = 'Hashtags Footer';
  tagsTxt.setPluginData('role', 'hashtags_footer');
  nodes.push(tagsTxt);

  const grp = _eslGroup(nodes, title || 'Flashcards Block');
  if (grp) {
    grp.setPluginData('role', 'esl_activity_block');
    grp.setPluginData('created_at', String(Date.now()));
  }
  _eslScrollTo(nodes);
  figma.notify('✅ Flashcards created!', { timeout: 2500 });
  return { ok: true, success: true, nodeId: grp ? grp.id : (nodes[0] && nodes[0].id), x: Math.round(grp ? grp.x : BX), y: Math.round(grp ? grp.y : BY), width: Math.round(BLOCK_W), height: Math.round(BLOCK_H) };
}

// ─── drawESLFillBlanks (Nordic Pastel Theme) ────────────────────────────
async function drawESLFillBlanks(params) {
  await _eslEnsureFonts();
  const { title, level, instruction, word_bank = [], sentences = [], hashtags = [], design = {} } = params;

  // Theme 1: Nordic Pastel
  const C = {
    bg_block: '#fafaf9', bg_card: '#ffffff', border: '#e5e7eb',
    accent: '#5eead4', header_bg: '#ffffff', text_primary: '#0f172a',
    text_secondary: '#334155', text_hashtags: '#64748b',
    ...(design.colors || {})
  };
  const nodes = [];
  const PAD = 32; const ROW_H = 72; const BLOCK_W = params.width || 1200;
  const CHIP_H = 48;
  const BLOCK_H = 80 + 52 + 20 + 120 + 20 + sentences.length * (ROW_H + 12) + 80;
  const origin = _eslGetOrigin(BLOCK_W, BLOCK_H, params);
  const BX = origin.x; const BY = origin.y;

  const bg = _eslMakeRect(BX, BY, BLOCK_W, BLOCK_H, C.bg_block, 24);
  bg.name = 'Block Container Background'; bg.setPluginData('role', 'block_container');
  _eslMakeStroke(bg, C.border, 2.0); nodes.push(bg);

  const hdrH = 72;
  const hdr = _eslMakeRect(BX + PAD, BY + PAD, BLOCK_W - PAD * 2, hdrH, C.header_bg, 16);
  _eslMakeStroke(hdr, C.accent, 2.0); nodes.push(hdr);

  // Back to menu btn (rightmost)
  const menuBtnW = 148;
  const menuBtnX = BX + BLOCK_W - PAD - menuBtnW - 10;
  const menuBtnY = BY + PAD + 16;
  const mBtn = _eslMakeRect(menuBtnX, menuBtnY, menuBtnW, 40, C.menu_btn_bg || C.accent || '#5eead4', 20);
  mBtn.setPluginData('role', 'back_to_menu');
  nodes.push(mBtn);
  nodes.push(_eslMakeText('📑 В МЕНЮ ↩', menuBtnX + 10, menuBtnY + 11, menuBtnW - 20, 20, '#0f172a', 12, 'Bold'));

  // Unique block ID for all draggable word chips and reset button
  const blockId = 'fill_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);

  // Reset button: [🔄 СБРОС]
  const resetBtnW = 140;
  const resetBtnX = menuBtnX - resetBtnW - 12;
  const resetBtn = _eslMakeRect(resetBtnX, menuBtnY, resetBtnW, 40, '#fca5a5', 20);
  resetBtn.setPluginData('role', 'reset_interactive');
  resetBtn.setPluginData('blockId', blockId);
  nodes.push(resetBtn);
  const resetTxt = _eslMakeText('🔄 СБРОС', resetBtnX + 10, menuBtnY + 11, resetBtnW - 20, 20, '#0f172a', 12, 'Bold');
  resetTxt.setPluginData('role', 'reset_interactive');
  resetTxt.setPluginData('blockId', blockId);
  nodes.push(resetTxt);

  const titleAvailW = resetBtnX - (BX + PAD + 16) - 16;
  const bloomTag = (params.bloom_badge ? params.bloom_badge + '  •  ' : '');
  const cleanTitle = formatBlockTitleWithLevel(bloomTag, title || 'Fill in the Blanks', level);

  let tFontSize = 22;
  if (cleanTitle.length > 55) tFontSize = 16;
  else if (cleanTitle.length > 40) tFontSize = 18;
  else if (cleanTitle.length > 30) tFontSize = 20;

  const titleTxt = _eslMakeText(
    cleanTitle,
    BX + PAD + 16, BY + PAD + (hdrH - tFontSize - 6) / 2, titleAvailW, 40, C.text_primary,
    tFontSize, 'Bold'
  );
  titleTxt.name = 'Block Title';
  titleTxt.setPluginData('role', 'block_title');
  nodes.push(titleTxt);

  const iY = BY + PAD + hdrH + 12;
  const instr = _eslMakeRect(BX + PAD, iY, BLOCK_W - PAD * 2, 42, '#f8fafc', 12);
  nodes.push(instr);
  nodes.push(_eslMakeText('👉 ' + (instruction || 'Drag and drop the words into the correct blanks.'), BX + PAD + 14, iY + 11, BLOCK_W - PAD * 2 - 28, 22, '#1e293b', 14, 'Medium'));

  // Draggable Word Chips Bank
  const wbY = iY + 54;
  const wb = _eslMakeRect(BX + PAD, wbY, BLOCK_W - PAD * 2, 100, '#ffffff', 16);
  _eslMakeStroke(wb, '#e2e8f0', 2.0); nodes.push(wb);

  nodes.push(_eslMakeText('📝 WORD BANK (Drag words onto sentences):', BX + PAD + 16, wbY + 12, BLOCK_W - PAD * 2 - 32, 24, '#64748b', 14, 'Bold'));

  let chipX = BX + PAD + 16;
  let chipY = wbY + 40;
  const wordChipNodes = [];

  // Create Word Chips as solid FrameNodes
  for (let i = 0; i < word_bank.length; i++) {
    const word = word_bank[i];
    const estW = Math.max(100, word.length * 14 + 36);

    if (chipX + estW > BX + BLOCK_W - PAD - 16) {
      chipX = BX + PAD + 16;
      chipY += CHIP_H + 12;
      wb.resize(BLOCK_W - PAD * 2, (chipY - wbY) + CHIP_H + 16);
    }

    const chipFrame = figma.createFrame();
    chipFrame.name = 'Word: ' + word;
    chipFrame.resize(estW, CHIP_H);
    chipFrame.x = chipX;
    chipFrame.y = chipY;
    chipFrame.clipsContent = false;
    chipFrame.cornerRadius = 24;
    chipFrame.fills = [{ type: 'SOLID', color: hexToRgb('#f1f5f9') }];
    _eslMakeStroke(chipFrame, '#94a3b8', 2.0);
    chipFrame.effects = [{
      type: 'DROP_SHADOW', color: { r: 0, g: 0, b: 0, a: 0.1 },
      offset: { x: 0, y: 3 }, radius: 6, spread: 0, visible: true, blendMode: 'NORMAL'
    }];

    const chipTxt = _eslMakeText(word, 0, 11, estW, 26, '#0f172a', 18, 'Bold');
    chipTxt.textAlignHorizontal = 'CENTER';
    chipTxt.locked = true; // LOCKED! Cannot be clicked or moved separately from chipFrame
    chipFrame.appendChild(chipTxt);

    chipFrame.setPluginData('role', 'draggable_word_chip');
    chipFrame.setPluginData('blockId', blockId);
    chipFrame.setPluginData('chipIndex', String(i));
    chipFrame.setPluginData('initialX', String(chipX));
    chipFrame.setPluginData('initialY', String(chipY));
    chipFrame.setPluginData('initialRelX', String(chipX - BX));
    chipFrame.setPluginData('initialRelY', String(chipY - BY));

    wordChipNodes.push(chipFrame);
    chipX += estW + 16;
  }

  // Adjust Sentences Start Y based on Word Bank Height
  const sentY = wb.y + wb.height + 24;

  // Sentences (PUSHED TO NODES FIRST so sentence rows are LOWER in z-index)
  for (let i = 0; i < sentences.length; i++) {
    const s = sentences[i];
    const sy = sentY + i * (ROW_H + 12);
    const rowBg = '#ffffff';

    const sRow = _eslMakeRect(BX + PAD, sy, BLOCK_W - PAD * 2 - 280, ROW_H, rowBg, 16);
    _eslMakeStroke(sRow, '#e2e8f0', 1.5); nodes.push(sRow);

    let sentenceText = s.sentence_with_blank || '';
    if (!sentenceText.includes('__') && s.answer) {
      sentenceText = sentenceText.replace(s.answer, '___________');
    }
    sentenceText = sentenceText.replace(/_+/g, '___________');

    nodes.push(_eslMakeText(String(i + 1) + '.  ' + sentenceText, BX + PAD + 24, sy + 24, BLOCK_W - PAD * 2 - 320, 30, '#0f172a', 20, 'Medium'));

    // Hidden Answer Box (Right side)
    const ansBox = _eslMakeRect(BX + BLOCK_W - PAD - 268, sy, 256, ROW_H, '#ffffff', 16);
    _eslMakeStroke(ansBox, '#e2e8f0', 1.5); nodes.push(ansBox);

    const ansTxt = _eslMakeText('✅ ' + (s.answer || ''), BX + BLOCK_W - PAD - 256, sy + 24, 244, 30, '#0f172a', 18, 'Bold');
    ansBox.setPluginData('role', 'answer_box');
    ansTxt.setPluginData('role', 'answer_text');
    ansTxt.visible = false;
    ansBox.name = 'Answer Container';
    ansTxt.name = 'Answer Text';
    nodes.push(ansTxt);
  }

  // NOW PUSH WORD CHIPS TO NODES AFTER SENTENCES
  // In Figma layer tree, nodes pushed later have HIGHER z-index, so chips are ALWAYS on top!
  for (const chip of wordChipNodes) {
    nodes.push(chip);
  }

  const finalTotalH = (sentY + sentences.length * (ROW_H + 12)) - BY + 60;
  bg.resize(BLOCK_W, finalTotalH);

  const tY = BY + finalTotalH - 48;
  const tBg = _eslMakeRect(BX + PAD, tY, BLOCK_W - PAD * 2, 36, '#f8fafc', 12);
  nodes.push(tBg);
  const tagsTxt = _eslMakeText((hashtags.join(' ') || '#fillblanks #english #exercise'), BX + PAD + 14, tY + 8, BLOCK_W - PAD * 2 - 28, 20, C.text_hashtags, 14);
  tagsTxt.name = 'Hashtags Footer';
  tagsTxt.setPluginData('role', 'hashtags_footer');
  nodes.push(tagsTxt);

  const grp = _eslGroup(nodes, title || 'Fill Blanks Block');
  if (grp) {
    grp.setPluginData('blockId', blockId);
    grp.setPluginData('role', 'esl_activity_block');
    grp.setPluginData('created_at', String(Date.now()));
    // GUARANTEE: Move draggable word chips to the VERY END of grp.children (topmost z-index in Figma)!
    for (const chip of wordChipNodes) {
      try { grp.appendChild(chip); } catch (e) { }
    }
  }
  _eslScrollTo(nodes);
  figma.notify('✅ Fill-in-the-blanks created!', { timeout: 2500 });
  return { ok: true, success: true, nodeId: grp ? grp.id : (nodes[0] && nodes[0].id), x: Math.round(grp ? grp.x : BX), y: Math.round(grp ? grp.y : BY), width: Math.round(BLOCK_W), height: Math.round(finalTotalH) };
}

// ─── drawESLSpeakingCards (Warmup / Speaking Cards — Light Theme) ──────────
async function drawESLSpeakingCards(params) {
  await _eslEnsureFonts();
  const { title, level, instruction, cards = [], hashtags = [], design = {} } = params;

  // Theme 1: Nordic Pastel
  const C = {
    bg_block: '#fafaf9', border: '#e5e7eb',
    accent: '#5eead4', header_bg: '#ffffff',
    text_primary: '#0f172a', text_secondary: '#334155', text_hashtags: '#64748b',
    ...(design.colors || {})
  };
  const nodes = [];

  const CARD_W = 460; const CARD_H = 340;
  const PAD = 32;
  const BLOCK_W = params.width || 740;
  const BLOCK_H = 80 + 52 + 24 + CARD_H + 80 + 60;
  const origin = _eslGetOrigin(BLOCK_W, BLOCK_H, params);
  const BX = origin.x; const BY = origin.y;

  // Background
  const bg = _eslMakeRect(BX, BY, BLOCK_W, BLOCK_H, C.bg_block, 24);
  bg.name = 'Block Container Background';
  bg.setPluginData('role', 'block_container');
  _eslMakeStroke(bg, C.border, 2.0);
  nodes.push(bg);

  // Header
  const hdrH = 72;
  const hdr = _eslMakeRect(BX + PAD, BY + PAD, BLOCK_W - PAD * 2, hdrH, C.header_bg, 16);
  _eslMakeStroke(hdr, C.accent, 2.0);
  nodes.push(hdr);

  // Back to menu btn
  const menuBtnW = 148;
  const menuBtnX = BX + BLOCK_W - PAD - menuBtnW - 10;
  const menuBtnY = BY + PAD + 16;
  const mBtn = _eslMakeRect(menuBtnX, menuBtnY, menuBtnW, 40, C.menu_btn_bg || C.accent || '#5eead4', 20);
  mBtn.setPluginData('role', 'back_to_menu');
  nodes.push(mBtn);
  nodes.push(_eslMakeText('📑 В МЕНЮ ↩', menuBtnX + 8, menuBtnY + 11, menuBtnW - 16, 20, '#0f172a', 12, 'Bold'));

  // Unique block ID for speaking cards stack and reset button
  const blockId = 'spk_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);

  // Reset button: [🔄 СБРОС]
  const resetBtnW = 140;
  const resetBtnX = menuBtnX - resetBtnW - 12;
  const resetBtn = _eslMakeRect(resetBtnX, menuBtnY, resetBtnW, 40, '#fca5a5', 20);
  resetBtn.setPluginData('role', 'reset_interactive');
  resetBtn.setPluginData('blockId', blockId);
  nodes.push(resetBtn);
  const resetTxt = _eslMakeText('🔄 СБРОС', resetBtnX + 10, menuBtnY + 11, resetBtnW - 20, 20, '#0f172a', 12, 'Bold');
  resetTxt.setPluginData('role', 'reset_interactive');
  resetTxt.setPluginData('blockId', blockId);
  nodes.push(resetTxt);

  const titleAvailW = resetBtnX - (BX + PAD + 16) - 16;
  const bloomTag = (params.bloom_badge ? params.bloom_badge + '  •  ' : '');
  const cleanTitle = formatBlockTitleWithLevel(bloomTag, title || '🗣 Speaking Cards', level);

  let tFontSize = 22;
  if (cleanTitle.length > 55) tFontSize = 16;
  else if (cleanTitle.length > 40) tFontSize = 18;
  else if (cleanTitle.length > 30) tFontSize = 20;

  const titleTxt = _eslMakeText(
    cleanTitle,
    BX + PAD + 16, BY + PAD + (hdrH - tFontSize - 6) / 2, titleAvailW, 40, C.text_primary,
    tFontSize, 'Bold'
  );
  titleTxt.name = 'Block Title';
  titleTxt.setPluginData('role', 'block_title');
  nodes.push(titleTxt);

  // Instruction banner
  const iY = BY + PAD + hdrH + 12;
  const instr = _eslMakeRect(BX + PAD, iY, BLOCK_W - PAD * 2, 40, '#f8fafc', 12);
  nodes.push(instr);
  nodes.push(_eslMakeText('🗣 ' + (instruction || 'Discuss the questions with your partner!'),
    BX + PAD + 14, iY + 10, BLOCK_W - PAD * 2 - 28, 22, '#1e293b', 14, 'Medium'));

  // Cards Pile
  const cardsStartY = iY + 60;
  const pileCenterX = BX + (BLOCK_W - CARD_W) / 2;

  // Draw cards in reverse order so card 1 is on top
  for (let i = cards.length - 1; i >= 0; i--) {
    const card = cards[i];

    // Offset for the pile effect
    const offset = i * 8;
    const cX = pileCenterX + offset;
    const cY = cardsStartY + offset;
    const cardColor = card.color || '#5eead4';

    // Single solid FrameNode for the entire card
    const cardFrame = figma.createFrame();
    cardFrame.name = `Card ${i + 1}`;
    cardFrame.resize(CARD_W, CARD_H);
    cardFrame.x = cX;
    cardFrame.y = cY;
    cardFrame.clipsContent = false;
    cardFrame.cornerRadius = 24;
    cardFrame.fills = [{ type: 'SOLID', color: hexToRgb(cardColor) }];
    _eslMakeStroke(cardFrame, '#ffffff', 4);
    cardFrame.effects = [{
      type: 'DROP_SHADOW', color: { r: 0, g: 0, b: 0, a: 0.12 },
      offset: { x: 0, y: 10 }, radius: 20, spread: 0, visible: true, blendMode: 'NORMAL'
    }];

    // Inner white container
    const innerBg = _eslMakeRect(16, 16, CARD_W - 32, CARD_H - 32, '#ffffff', 16);
    innerBg.locked = true; // LOCKED! Cannot be selected or dragged separately
    cardFrame.appendChild(innerBg);

    // Illustration or Emoji
    let qStartY = 110;
    if (card.image_base64) {
      try {
        const bytes = base64ToUint8Array(card.image_base64);
        const img = figma.createImage(bytes);
        const imgFrame = figma.createFrame();
        imgFrame.name = 'Card Illustration';
        imgFrame.resize(80, 80);
        imgFrame.x = 28;
        imgFrame.y = 28;
        imgFrame.cornerRadius = 16;
        imgFrame.fills = [{ type: 'IMAGE', imageHash: img.hash, scaleMode: 'FIT' }];
        imgFrame.locked = true; // LOCKED!
        cardFrame.appendChild(imgFrame);
        qStartY = 120;
      } catch (e) { }
    } else {
      const emojiTxt = _eslMakeText(card.emoji || '💬', 32, 32, 60, 60, '#0f172a', 40, 'Regular');
      emojiTxt.locked = true; // LOCKED!
      cardFrame.appendChild(emojiTxt);
    }

    // English Question (Very large font)
    const qTxt = _eslMakeText(
      card.question || '',
      32, qStartY, CARD_W - 64, 130,
      '#0f172a', 24, 'Bold'
    );
    qTxt.locked = true; // LOCKED!
    cardFrame.appendChild(qTxt);

    // Follow-up question (if exists)
    if (card.follow_up) {
      const fuTxt = _eslMakeText(
        '💡 ' + card.follow_up,
        32, CARD_H - 72, CARD_W - 64, 50,
        '#334155', 18, 'Medium'
      );
      fuTxt.locked = true; // LOCKED!
      cardFrame.appendChild(fuTxt);
    }

    // Rotation for pile effect
    const rot = (Math.random() * 6 - 3) * (Math.PI / 180);
    cardFrame.rotation = rot;

    cardFrame.setPluginData('role', 'speaking_card');
    cardFrame.setPluginData('blockId', blockId);
    cardFrame.setPluginData('cardIndex', String(i));
    cardFrame.setPluginData('initialX', String(cX));
    cardFrame.setPluginData('initialY', String(cY));
    cardFrame.setPluginData('initialRelX', String(cX - BX));
    cardFrame.setPluginData('initialRelY', String(cY - BY));
    cardFrame.setPluginData('initialRotation', String(rot));

    nodes.push(cardFrame);
  }

  // Hashtags footer
  const tY = BY + BLOCK_H - 46;
  const tBg = _eslMakeRect(BX + PAD, tY, BLOCK_W - PAD * 2, 36, '#f1f5f9', 8);
  _eslMakeStroke(tBg, '#e2e8f0', 1); nodes.push(tBg);
  const tagsTxt = _eslMakeText((hashtags.join(' ') || '#speaking #warmup #discussion #english #esl'),
    BX + PAD + 12, tY + 8, BLOCK_W - PAD * 2 - 24, 20, C.text_hashtags, 12);
  tagsTxt.name = 'Hashtags Footer';
  tagsTxt.setPluginData('role', 'hashtags_footer');
  nodes.push(tagsTxt);

  const grp = _eslGroup(nodes, title || 'Speaking Cards Block');
  if (grp) {
    grp.setPluginData('blockId', blockId);
    grp.setPluginData('role', 'esl_activity_block');
    grp.setPluginData('created_at', String(Date.now()));
  }
  _eslScrollTo(nodes);
  figma.notify('✅ Speaking cards created!', { timeout: 2500 });
  return { ok: true, success: true, nodeId: grp ? grp.id : (nodes[0] && nodes[0].id), x: Math.round(grp ? grp.x : BX), y: Math.round(grp ? grp.y : BY), width: Math.round(BLOCK_W), height: Math.round(BLOCK_H) };
}

// ─── drawTimestampBlock (Light Educational Theme) ────────────────────────
async function drawTimestampBlock(params = {}) {
  await _eslEnsureFonts();
  const now = new Date();
  const hours = String(now.getHours()).padStart(2, '0');
  const minutes = String(now.getMinutes()).padStart(2, '0');
  const timeStr = params.time || `${hours}:${minutes}`;
  const dateStr = params.date || now.toLocaleDateString('ru-RU', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
  });
  const shortDate = params.shortDate || `${now.getDate()} ${now.toLocaleString('ru-RU', { month: 'short' })} ${now.getFullYear()}`;

  const BLOCK_W = 460;
  const BLOCK_H = 154;
  const PAD = 20;

  // Determine smart placement: next to active selection, or in viewport center
  const center = figma.viewport.center;
  let BX = Math.round(center.x - BLOCK_W / 2);
  let BY = Math.round(center.y - BLOCK_H / 2);

  if (figma.currentPage.selection && figma.currentPage.selection.length > 0) {
    const sel = figma.currentPage.selection[0];
    if (typeof sel.x === 'number' && typeof sel.y === 'number') {
      BX = Math.round(sel.x + (sel.width || 400) + 40);
      BY = Math.round(sel.y);
    }
  }

  const nodes = [];

  // 1. Background Container (Light Theme: white background with subtle border)
  const bg = _eslMakeRect(BX, BY, BLOCK_W, BLOCK_H, '#ffffff', 20);
  _eslMakeStroke(bg, '#cbd5e1', 2);
  bg.setPluginData('role', 'block_container');
  bg.name = 'Container';
  nodes.push(bg);

  // 2. Top Header (Tag on left, Back to Menu on right)
  const tagW = 150;
  const tagH = 26;
  const tagBg = _eslMakeRect(BX + PAD, BY + 18, tagW, tagH, '#eff6ff', 13);
  _eslMakeStroke(tagBg, '#bfdbfe', 1.2);
  nodes.push(tagBg);

  const tagTxt = _eslMakeText('🕒 ВРЕМЯ УРОКА', BX + PAD + 10, BY + 23, tagW - 20, 16, '#2563eb', 11, 'Bold');
  nodes.push(tagTxt);

  // Back to Menu button (User Rule 4)
  const menuBtnW = 110;
  const menuBtnX = BX + BLOCK_W - PAD - menuBtnW;
  const menuBtn = _eslMakeRect(menuBtnX, BY + 18, menuBtnW, tagH, '#2563eb', 10);
  _eslMakeStroke(menuBtn, '#1d4ed8', 1.2);
  menuBtn.setPluginData('role', 'back_to_menu');
  menuBtn.name = 'В МЕНЮ ↩';
  nodes.push(menuBtn);

  const menuTxt = _eslMakeText('📑 В МЕНЮ ↩', menuBtnX + 6, BY + 23, menuBtnW - 12, 16, '#ffffff', 11, 'Bold');
  menuTxt.setPluginData('role', 'back_to_menu');
  nodes.push(menuTxt);

  // 3. Center Content: Big Bold Time on left, Date & Subtitle on right (High Contrast)
  const timeTxt = _eslMakeText(timeStr, BX + PAD + 2, BY + 58, 140, 56, '#0f172a', 46, 'Bold');
  nodes.push(timeTxt);

  // Divider vertical bar
  const divLine = _eslMakeRect(BX + PAD + 148, BY + 60, 2, 52, '#e2e8f0', 1);
  nodes.push(divLine);

  // Date line & note
  const dateTxt = _eslMakeText(dateStr, BX + PAD + 162, BY + 60, BLOCK_W - PAD * 2 - 162, 24, '#0f172a', 15, 'Bold');
  nodes.push(dateTxt);

  const subTxt = _eslMakeText('Зафиксировано через ESL AI Assistant', BX + PAD + 162, BY + 88, BLOCK_W - PAD * 2 - 162, 18, '#64748b', 12, 'Regular');
  nodes.push(subTxt);

  // 4. Group all nodes together
  const displayTitle = `Урок ${timeStr} • ${shortDate}`;
  const group = _eslGroup(nodes, `🕒 ${displayTitle}`);
  if (group) {
    group.setPluginData('role', 'timestamp_block');
    group.setPluginData('category', 'Таймлайн');
    group.setPluginData('custom_title', displayTitle);
    group.setPluginData('time', timeStr);
    group.setPluginData('date', dateStr);
    group.setPluginData('short_date', shortDate);
    group.setPluginData('created_at', String(Date.now()));

    // Automatically refresh Table of Contents so this timestamp immediately appears under "🕒 ТАЙМЛАЙН"
    try {
      await refreshTableOfContents();
    } catch (e) { }

    figma.currentPage.selection = [group];
    figma.notify(`🕒 Отметка времени [${timeStr}] создана и добавлена в оглавление!`, { timeout: 2500 });
  }
  return { ok: true, success: true, nodeId: group ? group.id : null };
}

// ─── addTOCEntry ─────────────────────────────────────────────────────────
async function addTOCEntry(params) {
  await _eslEnsureFonts();
  const { category, title, target_node_id, marker = '__ESL_TOC__' } = params;

  // Find TOC group
  const tocGroup = figma.currentPage.children.find(c =>
    c.name && (c.name.startsWith(marker) || c.name.includes('ОГЛАВЛЕНИЕ'))
  );
  if (!tocGroup) return { ok: false, error: 'TOC not found' };

  // Find matching category column inside TOC
  let colHeader = null;
  let colBox = null;

  // Search inside TOC group for matching category
  const searchIn = tocGroup.children || figma.currentPage.findAll(n => n.getPluginData && n.getPluginData('role') === 'toc_item');

  // Add entry text below existing ones
  const targetNode = target_node_id ? figma.getNodeById(target_node_id) : null;

  // Rebuild TOC to include new entry
  figma.notify('📑 Refreshing TOC with new entry...', { timeout: 1500 });
  const result = await refreshTableOfContents();
  return { ok: true, success: true, ...result };
}



// ─────────────────────────────────────────────────────────────
// ESL FULL LESSON PACKAGE & TEACHER GUIDE GENERATOR
// ─────────────────────────────────────────────────────────────

// ─── cleanupCanvasOrphanSections ──────────────────────────────────────────
function cleanupCanvasOrphanSections() {
  try {
    const sections = figma.currentPage.children.filter(n =>
      n.type === "SECTION" &&
      (n.name.includes("УРОК") || n.name.includes("DIAGNO") || n.name.includes("DINO") || n.name.includes("9."))
    );
    let removed = 0;
    for (const sec of sections) {
      if (!sec.children || sec.children.length === 0) {
        sec.remove();
        removed++;
      }
    }
    return removed;
  } catch (e) {
    return 0;
  }
}

// ─── _drawSubBlockByAction helper ─────────────────────────────────────────
async function _drawSubBlockByAction(action, data) {
  let res = null;
  if (action === "DRAW_SPEAKING_CARDS") res = await drawESLSpeakingCards(data);
  else if (action === "DRAW_VOCAB_TABLE" || action === "DRAW_VOCABULARY_TABLE") res = await drawESLVocabularyTable(data);
  else if (action === "DRAW_QUIZ_PHOTO") res = await drawESLQuizPhoto(data);
  else if (action === "DRAW_FLIP_CARDS") res = await drawESLFlipCards(data);
  else if (action === "DRAW_FILL_BLANKS") res = await drawESLFillBlanks(data);
  if (res && res.nodeId) {
    return figma.getNodeById(res.nodeId);
  }
  return null;
}

// ─── Markdown Cleaner Helper for Figma ────────────────────────────────────
function cleanMarkdownForFigma(raw) {
  if (!raw) return "";
  let t = String(raw);
  t = t.replace(/\*\*\*([^*]+)\*\*\*/g, "$1");
  t = t.replace(/\*\*([^*]+)\*\*/g, "$1");
  t = t.replace(/\*([^*]+)\*/g, "$1");
  t = t.replace(/__([^_]+)__/g, "$1");
  t = t.replace(/_([^_]+)_/g, "$1");
  t = t.replace(/`([^`]+)`/g, "$1");
  t = t.replace(/\|[ -:|]+\|/g, "");
  t = t.replace(/\|/g, " • ");
  t = t.replace(/^[ \t]*#+\s*/gm, "");
  t = t.replace(/^[ \t]*[-*+]\s+/gm, "• ");
  t = t.replace(/\n{3,}/g, "\n\n");
  return t.trim();
}

// ─── drawTeacherGuideCard (Structured Pedagogical Guide) ───────────────────
async function drawTeacherGuideCard(params) {
  const x = params.x || 0;
  const y = params.y || 0;
  const width = params.width || 1350;
  const topic = params.topic || "English Lesson";
  const studentName = params.studentName || "Ученик";
  const studentAge = params.studentAge || "";
  const level = params.level || "A1";
  const rawGuideText = params.guideText || "";
  const guideText = cleanMarkdownForFigma(rawGuideText);

  await ensureFonts();

  const nodes = [];
  const pad = 28;

  // Header Banner: deep luxury navy with vibrant cyan border
  const hdrH = 74;
  const hdrBg = _eslMakeRect(x + pad, y + pad, width - pad * 2, hdrH, "#0f172a", 16);
  _eslMakeStroke(hdrBg, "#0284c7", 2.5);
  nodes.push(hdrBg);

  const headerTitle = _eslMakeText(
    "📋 ШПАРГАЛКА ПРЕПОДАВАТЕЛЯ (TEACHER GUIDE)",
    x + pad + 20, y + pad + 14, width - pad * 2 - 40, 24,
    "#ffffff", 18, "Bold"
  );
  nodes.push(headerTitle);

  const subTitle = _eslMakeText(
    `👤 ${studentName}${studentAge ? ' (' + studentAge + ' лет)' : ''}   •   🎓 Уровень: ${level}   •   ⏱️ 25–35 мин   •   🔒 Только для учителя`,
    x + pad + 20, y + pad + 42, width - pad * 2 - 40, 20,
    "#38bdf8", 13, "SemiBold"
  );
  nodes.push(subTitle);

  // Content area
  const contentY = y + pad + hdrH + 18;
  const contentW = width - pad * 2;

  // For wide cards (>= 1000px), use 2 balanced columns for supreme readability
  if (width >= 1000) {
    const colW = Math.floor((contentW - 28) / 2);

    // Split logically by section marker or paragraphs
    let col1Text = "", col2Text = "";
    const splitRegex = /(?:💡|МЕТОДИЧЕСКИЙ ФОКУС|ФОКУС ПРЕПОДАВАТЕЛЯ|3\.\s*💡)/i;
    const splitMatch = guideText.search(splitRegex);
    if (splitMatch > 60) {
      col1Text = guideText.slice(0, splitMatch).trim();
      col2Text = guideText.slice(splitMatch).trim();
    } else {
      const paras = guideText.split("\n\n");
      const mid = Math.ceil(paras.length / 2);
      col1Text = paras.slice(0, mid).join("\n\n").trim();
      col2Text = paras.slice(mid).join("\n\n").trim();
    }

    const col1Node = await _eslMakeText({
      text: col1Text || "План занятия сформирован автоматически методическим ассистентом.",
      fontSize: 15,
      fontWeight: "Regular",
      color: "#0f172a",
      x: x + pad,
      y: contentY,
      width: colW,
      autoHeight: true
    });
    nodes.push(col1Node);

    const col2Node = await _eslMakeText({
      text: col2Text || "Методические рекомендации к этапам занятия и индивидуальный фокус.",
      fontSize: 15,
      fontWeight: "Regular",
      color: "#0f172a",
      x: x + pad + colW + 28,
      y: contentY,
      width: colW,
      autoHeight: true
    });
    nodes.push(col2Node);

    const contentH = Math.max(col1Node.height || 0, col2Node.height || 0, 160);
    const totalH = Math.max(340, (contentY + contentH + pad) - y);

    const bg = _eslMakeRect(x, y, width, totalH, "#f8fafc", 24);
    _eslMakeStroke(bg, "#0284c7", 3.0);
    bg.name = "Teacher Guide Background";
    bg.setPluginData("role", "teacher_guide_container");

    const cardGroup = figma.group([bg, ...nodes], figma.currentPage);
    try { cardGroup.insertChild(0, bg); } catch (_) { }
    cardGroup.name = `📋 Методическая записка — ${studentName}`;
    return cardGroup;
  } else {
    // Single column for narrower cards
    const bodyNode = await _eslMakeText({
      text: guideText || "План занятия сформирован автоматически методическим ассистентом.",
      fontSize: 15,
      fontWeight: "Regular",
      color: "#0f172a",
      x: x + pad,
      y: contentY,
      width: contentW,
      autoHeight: true
    });
    nodes.push(bodyNode);

    const totalH = Math.max(340, (bodyNode.y + (bodyNode.height || 0) + pad) - y);
    const bg = _eslMakeRect(x, y, width, totalH, "#f8fafc", 24);
    _eslMakeStroke(bg, "#0284c7", 3.0);
    bg.name = "Teacher Guide Background";
    bg.setPluginData("role", "teacher_guide_container");

    const cardGroup = figma.group([bg, ...nodes], figma.currentPage);
    try { cardGroup.insertChild(0, bg); } catch (_) { }
    cardGroup.name = `📋 Методическая записка — ${studentName}`;
    return cardGroup;
  }
}

// ─── drawESLFullLesson (Unified Educational Worksheet Container) ───────────
async function drawESLFullLesson(params) {
  const topic = params.topic || "English Lesson";
  const studentName = params.student_name || "Ученик";
  const studentAge = params.student_age || "";
  const level = params.level || "A1";
  const goal = params.goal || "Комплексное занятие";
  const teacherGuide = params.teacher_guide || "";
  const subBlocks = params.sub_blocks || [];

  figma.notify(`🚀 Создаю единый комплексный урок для ${studentName}...`);
  await ensureFonts();

  // 1. Cleanup any orphaned ghost sections from previous runs
  cleanupCanvasOrphanSections();

  const BLOCK_W = 1350;
  const PAD = 44;
  const GAP = 36;
  const numSub = subBlocks.length;
  const isGrid2x2 = (numSub >= 3);

  // Master container width: 2 balanced columns (2824px) or single column (1438px)
  const masterW = isGrid2x2 ? (PAD * 2 + BLOCK_W * 2 + GAP) : (PAD * 2 + BLOCK_W);

  // Find smart non-overlapping position below existing canvas blocks, or replace existing block
  const estTotalH = isGrid2x2 ? 1800 : 1200;
  let baseX = 0;
  let baseY = 0;
  let oldNodeToRemove = null;

  if (params.replaceNodeId) {
    const oldNode = figma.getNodeById(params.replaceNodeId);
    if (oldNode) {
      baseX = oldNode.x;
      baseY = oldNode.y;
      oldNodeToRemove = oldNode;
    }
  }

  if (oldNodeToRemove === null) {
    const pos = (typeof getNextBlockPosition === "function")
      ? getNextBlockPosition(masterW, estTotalH)
      : (typeof findSmartNonOverlappingPosition === "function" ? findSmartNonOverlappingPosition(masterW, estTotalH, "BOTTOM") : { x: 0, y: 0 });
    baseX = pos.x;
    baseY = pos.y;
  }
  const headerH = 140;
  const contentStartY = baseY + PAD + headerH + 28;

  const col1X = baseX + PAD;
  const col2X = isGrid2x2 ? (baseX + PAD + BLOCK_W + GAP) : col1X;

  const createdBlockGroups = [];

  if (isGrid2x2) {
    // 2x2 Balanced Widescreen Grid:
    // Row 1: Block 0 (Col 1, Emerald) & Block 1 (Col 2, Amber)
    // Row 2: Block 2 (Col 1, Purple) & Teacher Guide (Col 2, Cyan)

    // Block 0: Warm-up / Speaking Cards -> Emerald Theme
    let b0 = null;
    if (subBlocks[0]) {
      const theme0 = {
        colors: {
          bg_block: '#ffffff',
          border: '#10b981',
          border_width: 3.0,
          accent: '#059669',
          header_bg: '#ecfdf5',
          text_primary: '#064e3b'
        }
      };
      const data0 = {
        ...(subBlocks[0].data || {}),
        x: col1X,
        y: contentStartY,
        width: BLOCK_W,
        is_sub_block: true,
        design: { ...(subBlocks[0].data?.design || {}), ...theme0 },
        bloom_badge: subBlocks[0].bloom_badge || subBlocks[0].data?.bloom_badge,
        bloom_color: subBlocks[0].bloom_color || subBlocks[0].data?.bloom_color
      };
      b0 = await _drawSubBlockByAction(subBlocks[0].action, data0);
      if (b0) createdBlockGroups.push(b0);
    }

    // Block 1: Vocabulary Table -> Warm Amber Theme
    let b1 = null;
    if (subBlocks[1]) {
      const theme1 = {
        colors: {
          bg_block: '#ffffff',
          border: '#f59e0b',
          border_width: 3.0,
          accent: '#d97706',
          header_bg: '#fffbeb',
          text_primary: '#78350f'
        }
      };
      const data1 = {
        ...(subBlocks[1].data || {}),
        x: col2X,
        y: contentStartY,
        width: BLOCK_W,
        is_sub_block: true,
        design: { ...(subBlocks[1].data?.design || {}), ...theme1 },
        bloom_badge: subBlocks[1].bloom_badge || subBlocks[1].data?.bloom_badge,
        bloom_color: subBlocks[1].bloom_color || subBlocks[1].data?.bloom_color
      };
      b1 = await _drawSubBlockByAction(subBlocks[1].action, data1);
      if (b1) createdBlockGroups.push(b1);
    }

    const row1H = Math.max(
      b0 && b0.height ? b0.height : 650,
      b1 && b1.height ? b1.height : 650
    );

    const row2Y = contentStartY + row1H + GAP;

    // Block 2: Quiz Photo / Practice -> Vivid Purple Theme
    let b2 = null;
    if (subBlocks[2]) {
      const theme2 = {
        colors: {
          bg_block: '#ffffff',
          border: '#8b5cf6',
          border_width: 3.0,
          accent: '#7c3aed',
          header_bg: '#f5f3ff',
          text_primary: '#4c1d95'
        }
      };
      const data2 = {
        ...(subBlocks[2].data || {}),
        x: col1X,
        y: row2Y,
        width: BLOCK_W,
        is_sub_block: true,
        design: { ...(subBlocks[2].data?.design || {}), ...theme2 },
        bloom_badge: subBlocks[2].bloom_badge || subBlocks[2].data?.bloom_badge,
        bloom_color: subBlocks[2].bloom_color || subBlocks[2].data?.bloom_color
      };
      b2 = await _drawSubBlockByAction(subBlocks[2].action, data2);
      if (b2) createdBlockGroups.push(b2);
    }

    // Block 3 (if present, Row 2, Col 2)
    let b3 = null;
    if (subBlocks[3]) {
      const extraData = {
        ...(subBlocks[3].data || {}),
        x: col2X,
        y: row2Y,
        width: BLOCK_W,
        is_sub_block: true,
        bloom_badge: subBlocks[3].bloom_badge || subBlocks[3].data?.bloom_badge,
        bloom_color: subBlocks[3].bloom_color || subBlocks[3].data?.bloom_color
      };
      b3 = await _drawSubBlockByAction(subBlocks[3].action, extraData);
      if (b3) createdBlockGroups.push(b3);
    }

    // Extra blocks if > 4
    let nextRowY = row2Y + Math.max(b2 && b2.height ? b2.height : 650, b3 && b3.height ? b3.height : 650) + GAP;
    for (let i = 4; i < subBlocks.length; i++) {
      const cX = (i % 2 === 0) ? col1X : col2X;
      const extraData = {
        ...(subBlocks[i].data || {}),
        x: cX,
        y: nextRowY,
        width: BLOCK_W,
        is_sub_block: true,
        bloom_badge: subBlocks[i].bloom_badge || subBlocks[i].data?.bloom_badge,
        bloom_color: subBlocks[i].bloom_color || subBlocks[i].data?.bloom_color
      };
      const eb = await _drawSubBlockByAction(subBlocks[i].action, extraData);
      if (eb) {
        createdBlockGroups.push(eb);
        if (i % 2 === 1) nextRowY += (eb.height || 650) + GAP;
      }
    }

    // Determine bottom of all student activities
    let maxActivitiesBottom = contentStartY + row1H;
    for (const b of createdBlockGroups) {
      if (b && typeof b.y === "number") {
        maxActivitiesBottom = Math.max(maxActivitiesBottom, b.y + (b.height || 0));
      }
    }

    // Teacher Guide: ALWAYS BELOW all student blocks, ACROSS THE ENTIRE WIDTH (Request 1)
    const guideY = maxActivitiesBottom + GAP;
    const guideW = masterW - PAD * 2;
    const guideCard = await drawTeacherGuideCard({
      x: col1X,
      y: guideY,
      width: guideW,
      topic: topic,
      studentName: studentName,
      studentAge: studentAge,
      level: level,
      guideText: teacherGuide
    });
    if (guideCard) createdBlockGroups.push(guideCard);

  } else {
    // 1-Column or 2-block layout:
    let curY = contentStartY;
    for (let i = 0; i < subBlocks.length; i++) {
      const data = { ...(subBlocks[i].data || {}), x: col1X, y: curY };
      const b = await _drawSubBlockByAction(subBlocks[i].action, data);
      if (b) {
        createdBlockGroups.push(b);
        curY += (b.height || 650) + GAP;
      }
    }

    // Teacher Guide under the blocks across full width (Request 1)
    const guideCard = await drawTeacherGuideCard({
      x: col1X,
      y: curY,
      width: masterW - PAD * 2,
      topic: topic,
      studentName: studentName,
      studentAge: studentAge,
      level: level,
      guideText: teacherGuide
    });
    if (guideCard) createdBlockGroups.push(guideCard);
  }

  // Calculate true dimensions across all created elements
  let maxX = baseX + masterW, maxY = baseY + 1200;
  for (const node of createdBlockGroups) {
    if (node && typeof node.x === "number") {
      maxX = Math.max(maxX, node.x + (node.width || 0));
      maxY = Math.max(maxY, node.y + (node.height || 0));
    }
  }

  const finalContentW = Math.max(masterW, (maxX - baseX) + PAD);
  const footerY = maxY + 24;
  const masterH = (footerY + 44 + PAD) - baseY;

  // Master Header: Unified, Light, Eye-Catching Header across the full width (Requests 2 & 3)
  const headerW = finalContentW - PAD * 2;
  const masterHdr = _eslMakeRect(baseX + PAD, baseY + PAD, headerW, headerH, "#f0f9ff", 20);
  _eslMakeStroke(masterHdr, "#2563eb", 3.5);

  // Left accent bar for executive visual prominence
  const accentStripe = _eslMakeRect(baseX + PAD, baseY + PAD, 10, headerH, "#2563eb", 10);

  const cleanMasterTopic = (topic || '').replace(/\s*[\(\[]([A-C][0-2])[\)\]]\s*$/i, '').trim();
  const titleTxt = _eslMakeText(
    `🌟 УРОК: ${cleanMasterTopic.toUpperCase()} — ${studentName}`,
    baseX + PAD + 28, baseY + PAD + 18, headerW - 220, 32,
    "#0f172a", 24, "Bold"
  );
  titleTxt.name = "Block Title";
  titleTxt.setPluginData("role", "block_title");

  const badgeY = baseY + PAD + 54;
  const badgeInfo = `👤 ${studentName}${studentAge ? ', ' + studentAge + ' лет' : ''}   •   🎓 Уровень: ${level}   •   ⏱️ 45 мин`;
  const subTxt = _eslMakeText(
    badgeInfo,
    baseX + PAD + 28, badgeY, headerW - 220, 22,
    "#0284c7", 14, "SemiBold"
  );

  // Dynamic Composition of Blocks inside the lesson (Request 2)
  const actionToLabel = {
    "DRAW_SPEAKING_CARDS": "💬 Разминка (Speaking Cards)",
    "DRAW_VOCAB_TABLE": "📚 Словарь (Vocabulary Table)",
    "DRAW_VOCABULARY_TABLE": "📚 Словарь (Vocabulary Table)",
    "DRAW_QUIZ_PHOTO": "📸 Квиз (Photo Quiz)",
    "DRAW_FLIP_CARDS": "🃏 Открывашки (Flip Cards)",
    "DRAW_FILL_BLANKS": "✏️ Пропуски (Fill in Blanks)"
  };
  const compositionParts = subBlocks.map(b => {
    const badge = b.bloom_badge || b.data?.bloom_badge;
    const baseLabel = actionToLabel[b.action] || b.action || "Задание";
    return badge ? `${badge}: ${baseLabel}` : baseLabel;
  });
  const hasBloom = subBlocks.some(b => b.bloom_badge || b.data?.bloom_badge);
  const compStr = compositionParts.length > 0
    ? (hasBloom ? `🧠 Траектория Блума: ${compositionParts.join("   ➔   ")}` : `🧩 Состав урока: ${compositionParts.join("   •   ")}`)
    : "🧩 Комплексный интерактивный урок";

  const compTxt = _eslMakeText(
    compStr,
    baseX + PAD + 28, baseY + PAD + 80, headerW - 220, 22,
    "#2563eb", 13, "Bold"
  );

  const goalTxt = _eslMakeText(
    `🎯 Цель: ${goal}`,
    baseX + PAD + 28, baseY + PAD + 106, headerW - 220, 22,
    "#475569", 13, "Medium"
  );

  // Return to Menu button in top right of the master header (Rule 4)
  const menuBtnW = 160;
  const menuBtnH = 48;
  const menuBtnX = baseX + PAD + headerW - menuBtnW - 24;
  const menuBtnY = baseY + PAD + Math.floor((headerH - menuBtnH) / 2);
  const mBtn = _eslMakeRect(menuBtnX, menuBtnY, menuBtnW, menuBtnH, "#2563eb", 12);
  _eslMakeStroke(mBtn, "#1d4ed8", 2.0);
  mBtn.setPluginData("role", "back_to_menu");

  const mBtnTxt = _eslMakeText(
    "📑 В МЕНЮ ↩",
    menuBtnX + 16, menuBtnY + 14, menuBtnW - 32, 20,
    "#ffffff", 14, "Bold"
  );

  const headerRowNodes = [masterHdr, accentStripe, titleTxt, subTxt, compTxt, goalTxt, mBtn, mBtnTxt];

  // Master Background: solid cool slate container with clear dark border
  const masterBg = _eslMakeRect(baseX, baseY, finalContentW, masterH, "#f1f5f9", 32);
  _eslMakeStroke(masterBg, "#64748b", 3.0);
  masterBg.name = "🖼️ Block Container Background";
  masterBg.setPluginData("role", "block_container");

  // Master Footer: Hashtags
  const footerBg = _eslMakeRect(baseX + PAD, footerY, finalContentW - PAD * 2, 44, "#e2e8f0", 10);
  _eslMakeStroke(footerBg, "#cbd5e1", 1.5);
  const footerTxt = _eslMakeText(
    `#lesson #урок #${studentName.toLowerCase()} #${level.toLowerCase()} #esl #english #warmup #vocab #quiz #interactive`,
    baseX + PAD + 16, footerY + 12, finalContentW - PAD * 2 - 32, 20,
    "#475569", 12, "Regular"
  );
  footerTxt.name = "Hashtags Footer";
  footerTxt.setPluginData("role", "hashtags_footer");

  // Gather all nodes for grouping
  const allMasterNodes = [
    masterBg,
    ...headerRowNodes,
    ...createdBlockGroups,
    footerBg,
    footerTxt
  ];

  // Group everything into ONE clean, unified master group
  const fullLessonGroup = figma.group(allMasterNodes, figma.currentPage);
  try { fullLessonGroup.insertChild(0, masterBg); } catch (_) { }
  const fullTitle = `🌟 УРОК: ${topic.toUpperCase()} — для ${studentName} (${level})`;
  fullLessonGroup.name = `${fullTitle} (Interactive Block)`;
  fullLessonGroup.setPluginData("role", "full_lesson");
  fullLessonGroup.setPluginData("is_full_lesson", "true");
  fullLessonGroup.setPluginData("created_at", String(Date.now()));

  // Run auto-fix for any internal background layers in sub-groups
  try { fixAllBackgroundLayers(); } catch (_) { }

  if (oldNodeToRemove) {
    try { oldNodeToRemove.remove(); } catch (_) { }
  }

  // Select the group on canvas without disorienting viewport jump
  try {
    figma.currentPage.selection = [fullLessonGroup];
  } catch (_) { }

  figma.notify(`🎉 Комплексный урок «${topic}» для ${studentName} готов!`, { timeout: 4000 });
  return { ok: true, success: true, nodeId: fullLessonGroup.id };
}

// ─── CREATE_TOC case handler (called via bridge) ─────────────────────────
async function createTOCBlock(params) {
  return await refreshTableOfContents();
}

// ─── fixAllBackgroundLayers ───────────────────────────────────────────────
function fixAllBackgroundLayers() {
  try {
    let fixedCount = 0;
    for (const group of figma.currentPage.children) {
      if (group.type === "GROUP" && group.children && group.children.length > 1) {
        const bgIdx = group.children.findIndex(c => {
          if (!c) return false;
          if (c.getPluginData && (c.getPluginData("role") === "block_container" || c.getPluginData("is_container") === "true")) return true;
          const n = (c.name || "").toLowerCase();
          return n.includes("background") || n.includes("подложка") || n.includes("container");
        });
        if (bgIdx > 0) {
          const bgNode = group.children[bgIdx];
          group.insertChild(0, bgNode);
          fixedCount++;
        }
      }
    }
    return fixedCount;
  } catch (e) {
    console.warn("Auto-fix background layers error:", e);
    return 0;
  }
}


async function handleCommand(cmd) {
  if (!cmd) return { success: false, error: "Пустая команда" };

  if (typeof cmd === "string" || cmd.rawText || (cmd.params && cmd.params.rawText)) {
    const raw = (typeof cmd === "string" ? cmd : (cmd.rawText || cmd.params.rawText)).trim();
    return await parseAndExecuteTextCommand(raw);
  }

  const { action, params } = cmd;

  try {
    switch (action) {
      case "find":
      case "search":
      case "find_and_zoom":
      case "zoom_to":
        return findAndZoom(params ? (params.query || params.text || params) : cmd.query);

      case "search_blocks":
      case "find_blocks":
        return searchAllBlocks(params ? (params.query || params.text || params) : cmd.query);

      case "get_index":
      case "index":
      case "board_index":
        return getBoardIndex();

      case "draw_kids_game":
      case "kids_game":
      case "a1_game":
      case "draw_a1_game":
        return await drawKidsEnglishA1Game();

      case "draw_english_quiz":
      case "quiz":
      case "english_quiz":
        return await drawEnglishVocabularyAndQuiz();

      case "add_circle":
      case "create_circle":
      case "circle":
        return await createShapeOnCanvas({ ...params, shapeType: "ELLIPSE" });

      case "add_rect":
      case "create_rect":
      case "rect":
        return await createShapeOnCanvas({ ...params, shapeType: "ROUNDED_RECTANGLE" });

      case "add_sticky":
      case "sticky":
        return await createShapeOnCanvas({ ...params, shapeType: "STICKY" });

      case "add_diamond":
      case "diamond":
        return await createShapeOnCanvas({ ...params, shapeType: "DIAMOND" });

      case "add_triangle":
      case "triangle":
        return await createShapeOnCanvas({ ...params, shapeType: "TRIANGLE_UP" });

      case "clear_board":
      case "clear":
      case " стереть":
        return await clearBoard();

      case "info":
      case "get_info":
        return getCanvasInfo();

      case "refresh_toc":
      case "toc":
      case "update_toc":
      case "table_of_contents":
        return await refreshTableOfContents();

      case "navigate_to_toc":
      case "go_to_toc":
      case "scroll_to_toc":
      case "focus_toc":
        return await navigateToTableOfContents();

      case "toggle_toc":
      case "hide_toc":
      case "show_toc": {
        const tocs = figma.currentPage.children.filter(n =>
          (n.getPluginData && (n.getPluginData("role") === "table_of_contents" || n.getPluginData("is_toc") === "true")) ||
          (n.name && (n.name.includes("ОГЛАВЛЕНИЕ") || n.name.includes("Table of Contents")))
        );
        if (tocs.length === 0) return { success: false, error: "TOC not found on canvas" };
        let targetVisibility;
        if (cmd.action === "hide_toc") targetVisibility = false;
        else if (cmd.action === "show_toc") targetVisibility = true;
        else targetVisibility = !tocs.some(n => n.visible);
        tocs.forEach(n => { try { n.visible = targetVisibility; } catch (e) { } });
        figma.ui.postMessage({ type: "TOC_STATUS", exists: true, isVisible: targetVisibility });
        return { success: true, isVisible: targetVisibility };
      }

      case "reset_quiz":
      case "reset_quizzes": {
        let root = figma.currentPage;
        if (cmd.params && (cmd.params.blockId || cmd.params.nodeId)) {
          const b = figma.getNodeById(cmd.params.blockId || cmd.params.nodeId);
          if (b) root = b;
        } else if (figma.currentPage.selection.length > 0) {
          let b = figma.currentPage.selection[0];
          while (b && b.parent && b.parent !== figma.currentPage) {
            b = b.parent;
          }
          if (b) root = b;
        }
        const options = (root && typeof root.findAll === "function") ? root.findAll(n => {
          if (!n.getPluginData) return false;
          const r = n.getPluginData("role") || "";
          return r === "quiz_option" || r === "prep_quiz_option" || r.includes("quiz_option") || n.getPluginData("isCorrect") !== "";
        }) : [];

        for (const opt of options) {
          try {
            opt.fills = [{ type: "SOLID", color: hexToRgb("#1e293b") }];
            opt.strokes = [{ type: "SOLID", color: hexToRgb("#334155") }];
            opt.strokeWeight = 1.5;
            if (opt.text) {
              const font = (opt.text.fontName && opt.text.fontName !== figma.mixed) ? opt.text.fontName : { family: "Inter", style: "Medium" };
              figma.loadFontAsync(font).then(() => {
                opt.text.fills = [{ type: "SOLID", color: { r: 1, g: 1, b: 1 } }];
              }).catch(() => {
                figma.loadFontAsync({ family: "Inter", style: "Regular" }).then(() => {
                  opt.text.fills = [{ type: "SOLID", color: { r: 1, g: 1, b: 1 } }];
                });
              });
            }
          } catch (e) { }
        }
        figma.currentPage.selection = [];
        figma.notify(`🔄 Ответы квиза сброшены (${options.length})!`, { timeout: 2000 });
        return { success: true, count: options.length };
      }

      case "reset_cats": {
        const covers = figma.currentPage.findAll(n =>
          (n.getPluginData && n.getPluginData("role") === "cat_cover") || (n.name && n.name.includes("Cat Cover"))
        );
        covers.forEach(c => { c.visible = true; });
        figma.currentPage.selection = [];
        figma.notify(`🔄 Все котики (${covers.length}) снова на месте! 🐱`, { timeout: 2000 });
        return { success: true, count: covers.length };
      }

      case "zoom_to_toc": {
        const tocTarget = figma.currentPage.children.find(c =>
          (c.getPluginData && c.getPluginData("role") === "toc_header") || (c.name && c.name.includes("ОГЛАВЛЕНИЕ"))
        );
        if (tocTarget) {
          figma.currentPage.selection = [tocTarget];
          figma.viewport.scrollAndZoomIntoView([tocTarget]);
          figma.notify("📑 Переход в Оглавление доски", { timeout: 2000 });
          return { success: true, targetId: tocTarget.id };
        }
        return { success: false, error: "Оглавление не найдено на текущей доске" };
      }

      case "fix_backgrounds": {
        const count = fixAllBackgroundLayers();
        return { success: true, fixedCount: count };
      }

      case "eval": {
        const evalCode = (cmd && cmd.code) || (cmd && cmd.params && cmd.params.code) || (params && params.code);
        if (!evalCode) return { success: false, error: "Код для выполнения не указан" };
        const AsyncFunction = Object.getPrototypeOf(async function () { }).constructor;
        const fn = new AsyncFunction("figma", "hexToRgb", "ensureFonts", "createShapeOnCanvas", "findAndZoom", "searchAllBlocks", "fixAllBackgroundLayers", "drawTimestampBlock", "drawESLQuizPhoto", "drawESLFlipCards", "drawESLVideoQuiz", "drawESLVocabularyTable", "drawESLFlashcards", "drawESLFillBlanks", "drawESLSpeakingCards", "drawESLFullLesson", "refreshTableOfContents", "getCanvasBounds", "findSmartNonOverlappingPosition", "_eslGetOrigin", evalCode);
        const res = await fn(figma, hexToRgb, ensureFonts, createShapeOnCanvas, findAndZoom, searchAllBlocks, fixAllBackgroundLayers, drawTimestampBlock, drawESLQuizPhoto, drawESLFlipCards, drawESLVideoQuiz, drawESLVocabularyTable, drawESLFlashcards, drawESLFillBlanks, drawESLSpeakingCards, drawESLFullLesson, refreshTableOfContents, getCanvasBounds, findSmartNonOverlappingPosition, _eslGetOrigin);
        try { fixAllBackgroundLayers(); } catch (_) { }
        return { success: true, result: res };
      }

      // ═══════════════════════════════════════════════════════
      // ESL FIGMA AI — Block Drawing Commands
      // ═══════════════════════════════════════════════════════

      case "UPDATE_BLOCK_IMAGES": {
        const { nodeId, images = [] } = cmd.params || {};
        let target = nodeId ? figma.getNodeById(nodeId) : null;
        if (!target && figma.currentPage.selection.length > 0) {
          target = figma.currentPage.selection[0];
        }
        if (!target) return { ok: false, success: false, error: "No target block selected" };

        const imgNodes = [];
        function findImgs(n) {
          if (!n) return;
          if (n.name && (n.name.includes("Illustration") || n.name.includes("Photo") || n.name.includes("Image") || n.name.includes("Cover"))) {
            if (n.type === "FRAME" || n.type === "RECTANGLE") imgNodes.push(n);
          }
          if (n.fills && Array.isArray(n.fills) && n.fills.some(f => f.type === "IMAGE")) {
            if (!imgNodes.includes(n)) imgNodes.push(n);
          }
          if (n.children) {
            for (const c of n.children) findImgs(c);
          }
        }
        findImgs(target);

        let updatedCount = 0;
        for (let i = 0; i < imgNodes.length && i < images.length; i++) {
          const b64 = images[i];
          if (!b64) continue;
          try {
            const bytes = base64ToUint8Array(b64);
            const img = figma.createImage(bytes);
            imgNodes[i].fills = [{ type: "IMAGE", imageHash: img.hash, scaleMode: "FILL" }];
            updatedCount++;
          } catch (e) { }
        }
        figma.notify(`🖼️ Обновлено ${updatedCount} изображений в блоке!`, { timeout: 2500 });
        return { ok: true, success: true, updatedCount };
      }

      case "PING":
        return { ok: true, success: true };

      case "FIND_TOC": {
        const marker = cmd.params && cmd.params.marker || "__ESL_TOC__";
        const tocNode = figma.currentPage.children.find(c =>
          c.name && (c.name.startsWith(marker) || c.name.includes("ОГЛАВЛЕНИЕ"))
        );
        if (tocNode) return { ok: true, success: true, nodeId: tocNode.id };
        return { ok: false, success: false, nodeId: null };
      }

      case "CREATE_TOC":
        return await createTOCBlock(cmd.params || {});

      case "DRAW_QUIZ_PHOTO":
        return await drawESLQuizPhoto(cmd.params || {});

      case "DRAW_FLIP_CARDS":
        return await drawESLFlipCards(cmd.params || {});

      case "DRAW_VIDEO_QUIZ":
        return await drawESLVideoQuiz(cmd.params || {});

      case "DRAW_VOCABULARY_TABLE":
        return await drawESLVocabularyTable(cmd.params || {});

      case "DRAW_FLASHCARDS":
        return await drawESLFlashcards(cmd.params || {});

      case "DRAW_FILL_BLANKS":
        return await drawESLFillBlanks(cmd.params || {});

      case "DRAW_SPEAKING_CARDS":
        return await drawESLSpeakingCards(cmd.params || {});

      case "DRAW_FULL_LESSON":
      case "DRAW_ESL_FULL_LESSON":
      case "draw_full_lesson":
      case "full_lesson":
        return await drawESLFullLesson(cmd.params || cmd);

      case "DRAW_TIMESTAMP":
      case "CREATE_TIMESTAMP_BLOCK":
      case "timestamp":
        return await drawTimestampBlock(cmd.params || {});

      case "ADD_TOC_ENTRY":
        return await addTOCEntry(cmd.params || {});

      case "REFRESH_TOC": {
        const r = await refreshTableOfContents();
        figma.ui.postMessage({ type: "COMMAND_RESULT", cmd_id: cmd.id, ...r, ok: r.success });
        return r;
      }

      case "EXPORT_NODE_IMAGE":
      case "CAPTURE_NODE":
      case "CAPTURE_CANVAS":
      case "CAPTURE_BOARD": {
        let target = null;
        const p = cmd.params || cmd || {};
        const targetId = p.nodeId || p.node_id || p.id;
        const role = p.role;
        const query = p.query || p.name;

        if (targetId) {
          target = figma.getNodeById(targetId);
        }
        if (!target && role) {
          target = figma.currentPage.children.find(n => n.getPluginData && n.getPluginData("role") === role);
        }
        if (!target && query) {
          const qLower = String(query).toLowerCase();
          target = figma.currentPage.children.find(n => n.name && n.name.toLowerCase().includes(qLower));
        }
        if (!target) {
          target = figma.currentPage.children.find(n =>
            (n.getPluginData && n.getPluginData("role") === "full_lesson") ||
            (n.name && (n.name.includes("УРОК") || n.name.includes("DIAGNOSTIC")))
          );
        }
        if (!target) {
          const sel = figma.currentPage.selection;
          if (sel && sel.length > 0) target = sel[0];
          else target = figma.currentPage.children[figma.currentPage.children.length - 1];
        }

        if (!target) {
          return { success: false, ok: false, error: "На холсте не найдено объектов для визуального снимка" };
        }

        try {
          const format = (p.format === "JPG") ? "JPG" : "PNG";
          const maxDim = p.width || 1600;
          const bytes = await target.exportAsync({
            format: format,
            constraint: { type: "WIDTH", value: maxDim }
          });

          let b64 = "";
          if (typeof figma.base64Encode === "function") {
            b64 = figma.base64Encode(bytes);
          } else {
            let binary = "";
            const len = bytes.byteLength;
            for (let i = 0; i < len; i++) {
              binary += String.fromCharCode(bytes[i]);
            }
            b64 = (typeof btoa === "function") ? btoa(binary) : "";
          }

          return {
            ok: true,
            success: true,
            nodeId: target.id,
            nodeName: target.name,
            width: Math.round(target.width || 0),
            height: Math.round(target.height || 0),
            format: format,
            bytesCount: bytes.byteLength,
            image_base64: b64
          };
        } catch (exportErr) {
          return { success: false, ok: false, error: "Ошибка экспорта визуального снимка: " + String(exportErr) };
        }
      }

      case "GET_SELECTED_IMAGES":
      case "EXPORT_SELECTED_IMAGES": {
        const p = cmd.params || cmd || {};
        const limit = typeof p.limit === "number" ? Math.max(1, Math.min(p.limit, 30)) : 12;
        const maxDim = typeof p.width === "number" ? p.width : 800;
        const sel = figma.currentPage.selection || [];
        const existingBackup = findBoardBackupGroup();

        const candidateNodes = sel.filter(n =>
          n !== existingBackup &&
          !(n.getPluginData && n.getPluginData("role") === "board_backup") &&
          !(n.name && (n.name.startsWith("🔒 [РЕЗЕРВНАЯ КОПИЯ ДОСКИ]") || n.name.startsWith("🔒 [БЭКАП ДОСКИ]")))
        );

        if (candidateNodes.length === 0) {
          return { ok: true, success: true, count: 0, items: [] };
        }

        const items = [];
        const targetNodes = candidateNodes.slice(0, limit);

        for (const node of targetNodes) {
          try {
            const bytes = await node.exportAsync({
              format: "JPG",
              constraint: { type: "WIDTH", value: maxDim }
            });

            let b64 = "";
            if (typeof figma.base64Encode === "function") {
              b64 = figma.base64Encode(bytes);
            } else {
              let binary = "";
              const len = bytes.byteLength;
              for (let i = 0; i < len; i++) {
                binary += String.fromCharCode(bytes[i]);
              }
              b64 = (typeof btoa === "function") ? btoa(binary) : "";
            }

            items.push({
              id: node.id,
              name: node.name || "Image",
              width: Math.round(node.width || 0),
              height: Math.round(node.height || 0),
              image_base64: b64,
              size: bytes.byteLength
            });
          } catch (itemErr) {
            console.warn("Failed to export node", node.name, itemErr);
          }
        }

        return {
          ok: true,
          success: true,
          total_selected: candidateNodes.length,
          count: items.length,
          items: items
        };
      }

      default:
        return { success: false, error: `Неизвестное действие: ${action}` };
    }
  } catch (err) {
    return { success: false, error: String(err) };
  }
}

async function parseAndExecuteTextCommand(raw) {
  if (!raw) return { success: false, error: "Пустая строка команды" };

  if (raw.startsWith("js ") || raw.startsWith("eval ")) {
    const code = raw.replace(/^(js|eval)\s+/, "");
    try {
      const AsyncFunction = Object.getPrototypeOf(async function () { }).constructor;
      const fn = new AsyncFunction("figma", "hexToRgb", "ensureFonts", "createShapeOnCanvas", code);
      const res = await fn(figma, hexToRgb, ensureFonts, createShapeOnCanvas);
      return { success: true, ok: true, result: res };
    } catch (err) {
      return { success: false, ok: false, error: String(err) };
    }
  }

  const lower = raw.toLowerCase().trim();

  if (lower.includes("детск") || /\b(a1|kids)\b/i.test(lower) || lower.includes("игра")) {
    return await drawKidsEnglishA1Game();
  }

  if (lower === "квиз" || lower === "quiz" || lower.includes("английск") || lower === "словарь") {
    return await drawEnglishVocabularyAndQuiz();
  }

  if (lower === "круг" || lower.startsWith("круг ") || lower === "circle" || lower.startsWith("circle ")) {
    const parts = raw.split(" ");
    const text = parts.slice(1).join(" ") || "Круг";
    return await createShapeOnCanvas({ shapeType: "ELLIPSE", size: 180, color: "#8b5cf6", text });
  }

  if (lower === "квадрат" || lower.startsWith("квадрат ") || lower === "rect" || lower.startsWith("rect ") || lower === "прямоугольник") {
    const parts = raw.split(" ");
    const text = parts.slice(1).join(" ") || "Прямоугольник";
    return await createShapeOnCanvas({ shapeType: "ROUNDED_RECTANGLE", width: 220, height: 140, color: "#3b82f6", text });
  }

  if (lower === "стикер" || lower.startsWith("стикер ") || lower === "sticky" || lower.startsWith("sticky ")) {
    const parts = raw.split(" ");
    const text = parts.slice(1).join(" ") || "Заметка";
    return await createShapeOnCanvas({ shapeType: "STICKY", text });
  }

  if (lower === "ромб" || lower === "diamond") {
    return await createShapeOnCanvas({ shapeType: "DIAMOND", size: 180, color: "#f59e0b", text: "Условие" });
  }

  if (lower === "треугольник" || lower === "triangle") {
    return await createShapeOnCanvas({ shapeType: "TRIANGLE_UP", size: 180, color: "#10b981", text: "Старт" });
  }

  if (lower === "очистить" || lower === "clear" || lower === "стереть") {
    return await clearBoard();
  }

  if (lower === "инфо" || lower === "info" || lower === "статус") {
    return getCanvasInfo();
  }

  return await createShapeOnCanvas({
    shapeType: "ROUNDED_RECTANGLE",
    width: 240,
    height: 100,
    color: "#1e293b",
    text: raw
  });
}

function sendDocInfo() {
  if (figma.ui) {
    try {
      figma.ui.postMessage({
        type: "DOC_INFO",
        title: figma.root.name || "Untitled",
        fileKey: figma.fileKey || ""
      });
    } catch (_) { }
  }
}

figma.ui.onmessage = async (msg) => {
  try {
    if (!msg) return;
    if (msg.type === "EXPORT_SELECTION_IMAGE") {
      let targetNode = null;
      if (msg.nodeId) {
        targetNode = figma.getNodeById(msg.nodeId);
      }
      if (!targetNode) {
        const sel = figma.currentPage.selection;
        if (sel && sel.length > 0) targetNode = sel[0];
      }
      if (!targetNode && lastSelectedImageId) {
        targetNode = figma.getNodeById(lastSelectedImageId);
      }
      if (!targetNode) {
        // Fallback: search for any MEDIA or Image node on the page
        targetNode = figma.currentPage.children.find(n =>
          (n.type === 'MEDIA' || (n.fills && Array.isArray(n.fills) && n.fills.some(f => f.type === 'IMAGE'))) &&
          !(typeof isInsideTOC === 'function' && isInsideTOC(n))
        );
      }

      if (targetNode) {
        try {
          const bytes = await targetNode.exportAsync({
            format: "JPG",
            constraint: { type: "WIDTH", value: 1200 }
          });
          let b64 = "";
          if (typeof figma.base64Encode === "function") {
            b64 = figma.base64Encode(bytes);
          } else {
            let binary = "";
            const len = bytes.byteLength;
            for (let i = 0; i < len; i++) {
              binary += String.fromCharCode(bytes[i]);
            }
            b64 = (typeof btoa === 'function') ? btoa(binary) : "";
          }
          figma.ui.postMessage({
            type: "SELECTED_IMAGE_DATA",
            base64: b64,
            name: targetNode.name || "Selected Image"
          });
          return;
        } catch (e) {
          console.warn("Failed to export target node image:", e);
        }
      }
      figma.ui.postMessage({
        type: "SELECTED_IMAGE_DATA",
        base64: "",
        name: ""
      });
      return;
    }
    if (msg.type === "REQUEST_DOC_INFO") {
      sendDocInfo();
      sendSelectionInfo();
      return;
    }
    if (msg.type === "SEARCH_BLOCKS" || msg.type === "SEARCH_BOARD") {
      const res = searchAllBlocks(msg.query);
      figma.ui.postMessage({
        type: "SEARCH_RESULTS_LIST",
        query: msg.query,
        results: res.results || []
      });
      return;
    }
    if (msg.type === "ZOOM_TO_BLOCK" || msg.type === "ZOOM_TO_NODE") {
      const targetId = msg.blockId || msg.nodeId;
      let target = targetId ? figma.getNodeById(targetId) : null;
      if (!target && msg.bestNodeId) target = figma.getNodeById(msg.bestNodeId);
      if (target) {
        figma.currentPage.selection = [target];
        figma.viewport.scrollAndZoomIntoView([target]);
        figma.notify("🎯 " + (target.name || "Блок"), { timeout: 2000 });
      }
      return;
    }
    if (msg.type === "CREATE_TIMESTAMP_BLOCK") {
      await drawTimestampBlock(msg);
      return;
    }
    if (msg.type === "SAVE_SETTINGS") {
      if (msg.bridgeUrl) {
        await figma.clientStorage.setAsync("bridge_url", msg.bridgeUrl);
      }
      return;
    }
    if (msg.type === "LOAD_SETTINGS") {
      const savedUrl = await figma.clientStorage.getAsync("bridge_url");
      figma.ui.postMessage({
        type: "SETTINGS_LOADED",
        bridgeUrl: savedUrl || ""
      });
      sendBackupStatus();
      return;
    }
    if (msg.type === "GET_BACKUP_STATUS") {
      sendBackupStatus();
      sendSelectionInfo();
      return;
    }
    if (msg.type === "GET_SELECTION_STATUS") {
      sendSelectionInfo();
      return;
    }
    if (msg.type === "CREATE_BOARD_BACKUP" || msg.type === "EXPORT_BOARD_TO_FILE") {
      await exportBoardToFile(msg.options || {});
      return;
    }
    if (msg.type === "RESTORE_BOARD_BACKUP") {
      await restoreBoardBackup();
      return;
    }
    if (msg.type === "RESTORE_BOARD_FROM_DATA") {
      await restoreBoardFromData(msg.data, msg.mediaMap || null);
      return;
    }
    if (msg.type === "RESIZE_UI") {
      const w = typeof msg.width === "number" ? Math.max(300, msg.width) : 320;
      const h = typeof msg.height === "number" ? Math.max(100, msg.height) : 160;
      figma.ui.resize(w, h);
      return;
    }
    if (msg.type === "NAVIGATE_TO_TOC" || msg.type === "GO_TO_TOC" || msg.type === "SCROLL_TO_TOC") {
      await navigateToTableOfContents();
      return;
    }
    if (msg.type === "REFRESH_TOC" || msg.type === "REFRESH_TOC_REQUEST") {
      const res = await refreshTableOfContents();
      figma.ui.postMessage({
        type: "TOC_REFRESHED",
        success: (res && res.success !== false),
        totalBlocks: (res && res.totalBlocks) || 0
      });
      figma.ui.postMessage({
        type: "TOC_STATUS",
        exists: true,
        isVisible: true
      });
      return;
    }
    if (msg.type === "TOGGLE_TOC_VISIBILITY" || msg.type === "TOGGLE_TOC") {
      const tocs = figma.currentPage.children.filter(n =>
        (n.getPluginData && (n.getPluginData("role") === "table_of_contents" || n.getPluginData("is_toc") === "true")) ||
        (n.name && (n.name.includes("ОГЛАВЛЕНИЕ") || n.name.includes("Table of Contents")))
      );
      if (tocs.length === 0) {
        figma.notify("⚠️ Оглавление ещё не создано на доске! Нажмите «Обновить оглавление».", { timeout: 2500 });
        figma.ui.postMessage({
          type: "TOC_STATUS",
          exists: false,
          isVisible: false
        });
        return;
      }
      const isCurrentlyVisible = tocs.some(n => n.visible);
      const targetVisibility = !isCurrentlyVisible;
      tocs.forEach(n => {
        try { n.visible = targetVisibility; } catch (e) { }
      });
      if (targetVisibility) {
        figma.notify("👁️ Оглавление показано на доске", { timeout: 1800 });
      } else {
        figma.notify("🙈 Оглавление скрыто от учеников", { timeout: 1800 });
      }
      figma.ui.postMessage({
        type: "TOC_STATUS",
        exists: true,
        isVisible: targetVisibility
      });
      return;
    }
    if (msg.type === "DELETE_SELECTION") {
      const sel = figma.currentPage.selection;
      if (sel && sel.length > 0) {
        const count = sel.length;
        for (const n of sel) {
          try { n.remove(); } catch (e) { }
        }
        figma.notify(`🗑️ Удалено элементов: ${count}`);
      } else {
        figma.notify("Ничего не выделено на доске");
      }
      return;
    }
    if (msg.type === "SAVE_AS_TEMPLATE") {
      const sel = figma.currentPage.selection;
      if (!sel || sel.length === 0) {
        figma.notify("⚠️ Выделите блок или группу на доске!");
        return;
      }
      const target = sel[0];
      figma.ui.postMessage({
        type: "TEMPLATE_SAVED_LOCAL",
        name: msg.name || target.name || "Новый шаблон",
        width: Math.round(target.width || 1200),
        height: Math.round(target.height || 600),
      });
      figma.notify(`✅ Шаблон «${msg.name || target.name}» успешно добавлен!`);
      return;
    }
    if (msg.type === "CLEAR_SELECTION") {
      figma.currentPage.selection = [];
      sendSelectionInfo();
      figma.notify("🌐 Область сброшена на всю доску", { timeout: 1500 });
      return;
    }
    if (msg.type === "INSERT_BADGE") {
      const level = msg.level || "A2";
      const colors = {
        "A1": "#10b981",
        "A2": "#06b6d4",
        "B1": "#3b82f6",
        "B2": "#8b5cf6",
        "C1": "#ec4899"
      };
      const col = colors[level] || "#8b5cf6";
      const shape = await createShapeOnCanvas({
        shapeType: "ROUNDED_RECTANGLE",
        width: 140,
        height: 52,
        color: col,
        textColor: "#ffffff",
        text: `LEVEL ${level}`,
        fontSize: 18
      });
      if (shape) {
        figma.currentPage.selection = [shape];
        figma.viewport.scrollAndZoomIntoView([shape]);
        figma.notify(`🏷️ Бейдж ${level} добавлен!`);
      }
      return;
    }
    if (msg.type === "INSERT_STICKER") {
      const text = msg.text || "💡 Важная заметка";
      const col = msg.color || "#f59e0b";
      const shape = await createShapeOnCanvas({
        shapeType: "STICKY",
        width: 200,
        height: 200,
        color: col,
        textColor: "#ffffff",
        text: text,
        fontSize: 16
      });
      if (shape) {
        figma.currentPage.selection = [shape];
        figma.viewport.scrollAndZoomIntoView([shape]);
        figma.notify(`📝 Заметка добавлена!`);
      }
      return;
    }
    if (msg.type === "EXEC_COMMAND" && msg.command) {
      const result = await handleCommand(msg.command);
      const isOk = result ? (result.ok !== false && result.success !== false) : true;
      figma.ui.postMessage({
        type: "COMMAND_RESULT",
        cmd_id: msg.command.id || null,
        ok: isOk,
        success: isOk,
        nodeId: result ? (result.nodeId || result.node_id) : null,
        error: result ? result.error : null,
        ...(typeof result === 'object' ? result : {})
      });
      if (msg.command.action === "refresh_toc" || msg.command.action === "update_toc") {
        figma.ui.postMessage({
          type: "TOC_REFRESHED",
          success: (result && result.success !== false),
          totalBlocks: (result && result.totalBlocks) || 0
        });
      }
      return;
    }
  } catch (err) {
    console.error("Plugin error:", err);
    figma.notify("❌ Ошибка: " + (err.message || String(err)), { error: true });
    try {
      figma.ui.postMessage({
        type: "COMMAND_RESULT",
        cmd_id: msg && msg.command ? msg.command.id : null,
        result: { success: false, error: String(err) }
      });
    } catch (e) { }
  }
};

async function refreshTableOfContents() {
  await Promise.all([
    figma.loadFontAsync({ family: "Inter", style: "Regular" }),
    figma.loadFontAsync({ family: "Inter", style: "Medium" }),
    figma.loadFontAsync({ family: "Inter", style: "Bold" })
  ]);

  const isFigJam = typeof figma.createShapeWithText === "function";

  // 1. Find existing TOC position or determine default
  let defaultBaseX = 4560;
  let defaultBaseY = -350;

  const oldTocs = figma.currentPage.children.filter(n =>
    (n.name && (n.name.includes("ОГЛАВЛЕНИЕ") || n.name.includes("Table of Contents"))) ||
    (n.getPluginData && (n.getPluginData("role") === "table_of_contents" || n.getPluginData("is_toc") === "true"))
  );

  if (oldTocs.length > 0) {
    defaultBaseX = oldTocs[0].x + 32;
    defaultBaseY = oldTocs[0].y + 28;
  }

  oldTocs.forEach(n => { try { n.remove(); } catch (e) { } });

  // Remove any orphan TOC backgrounds
  const orphanBgs = figma.currentPage.children.filter(n =>
    n.name && n.name.includes("Block Container Background") && (n.x === defaultBaseX - 32 || (n.getPluginData && n.getPluginData("is_toc") === "true"))
  );
  orphanBgs.forEach(n => { try { n.remove(); } catch (e) { } });

  // 2. Universal scanner: find all activity blocks (groups or container backgrounds)
  const children = figma.currentPage.children;
  const rawBlocks = [];

  for (const n of children) {
    if (n.name && (n.name.includes("ОГЛАВЛЕНИЕ") || n.name.includes("Table of Contents"))) continue;
    if (n.getPluginData && (n.getPluginData("role") === "table_of_contents" || n.getPluginData("is_toc") === "true")) continue;

    if (n.type === "GROUP" || n.type === "SECTION") {
      let titleNode = null;
      const role = (n.getPluginData ? n.getPluginData("role") : "") || "";
      const pCat = (n.getPluginData ? n.getPluginData("category") : "") || "";
      const nNameUpper = (n.name || "").toUpperCase();

      const isTimestamp = (role === "timestamp_block" || pCat.toLowerCase() === "таймлайн" || nNameUpper.includes("ОТМЕТКА ВРЕМЕНИ") || nNameUpper.includes("ВРЕМЯ УРОКА") || nNameUpper.includes("ТАЙМЛАЙН"));
      let timestampTime = "";
      let timestampDate = "";
      let timestampShortDate = "";

      if (isTimestamp) {
        if (n.getPluginData) {
          timestampTime = n.getPluginData("time") || "";
          timestampDate = n.getPluginData("date") || "";
          timestampShortDate = n.getPluginData("short_date") || "";
        }
        if (n.children && (!timestampTime || !timestampDate)) {
          for (const c of n.children) {
            const chars = (c.characters || (c.text ? c.text.characters : "") || "").trim();
            if (!timestampTime && /^\d{1,2}:\d{2}$/.test(chars)) {
              timestampTime = chars;
            } else if (!timestampDate && (chars.includes("202") || chars.includes("янв") || chars.includes("фев") || chars.includes("мар") || chars.includes("апр") || chars.includes("май") || chars.includes("июн") || chars.includes("июл") || chars.includes("авг") || chars.includes("сен") || chars.includes("окт") || chars.includes("ноя") || chars.includes("дек") || chars.includes("понедельник") || chars.includes("вторник") || chars.includes("среда") || chars.includes("четверг") || chars.includes("пятница") || chars.includes("суббота") || chars.includes("воскресенье"))) {
              timestampDate = chars;
            }
          }
        }
        if (!timestampTime) {
          const tm = (n.name || "").match(/\b(\d{1,2}:\d{2})\b/);
          if (tm) timestampTime = tm[1];
        }
      }

      if (n.children) {
        const candidates = n.children.filter(c => {
          const name = (c.name || "").toLowerCase();
          const r = (c.getPluginData ? c.getPluginData("role") : "") || "";
          if (r === "hashtags_footer" || r === "block_container" || r === "back_to_menu" || r === "reset_quiz" || r === "reset_cats" || r === "cat_cover") return false;
          if (name.includes("background") || name.includes("в меню") || name.includes("хештеги") || name.includes("hashtag") || name.includes("reset") || name.includes("сброс") || name.includes("cover") || name.includes("подложка")) return false;

          // STRICT FILTER: Exclude any node whose text is hashtags, menu buttons, or instruction badge
          const chars = (c.characters || (c.text ? c.text.characters : "") || "").trim();
          if (chars.startsWith("#") || chars.startsWith("🏷️") || (chars.match(/#/g) || []).length >= 2) return false;
          if (chars.includes("👉") || chars.includes("Click to reveal") || chars.includes("В МЕНЮ") || chars.includes("ОГЛАВЛЕНИЕ")) return false;
          return true;
        });

        // Priority 0: Explicit role = "block_title" or name = "Block Title"
        titleNode = candidates.find(c => (c.getPluginData && c.getPluginData("role") === "block_title") || c.name === "Block Title");

        // Priority 1: Topmost text node in header area (y < n.y + 140)
        if (!titleNode) {
          const topCandidates = candidates.filter(c => c.y < n.y + 140 && (c.characters || (c.text && c.text.characters)));
          topCandidates.sort((a, b) => a.y - b.y);
          if (topCandidates.length > 0) titleNode = topCandidates[0];
        }

        // Priority 2: Any non-hashtag text node with text
        if (!titleNode) {
          const textNodes = candidates.filter(c => (c.type === "TEXT" || (c.text && c.text.characters)) && ((c.characters || (c.text ? c.text.characters : "")).trim().length > 0));
          textNodes.sort((a, b) => a.y - b.y);
          if (textNodes.length > 0) titleNode = textNodes[0];
        }
      }

      let titleText = "";
      if (isTimestamp) {
        titleText = timestampTime ? `🕒 ${timestampTime} • ${timestampDate || timestampShortDate || "Время урока"}` : (n.name || "Время урока");
      } else if (titleNode) {
        titleText = titleNode.characters || (titleNode.text ? titleNode.text.characters : titleNode.name);
      }
      if (!titleText || titleText.toLowerCase().startsWith("group") || titleText.trim().startsWith("#")) {
        titleText = n.name.replace(/\(Interactive Block\)/gi, "").trim();
      }
      if (titleText.startsWith("#") || (titleText.match(/#/g) || []).length >= 2) {
        titleText = n.name.replace(/\(Interactive Block\)/gi, "").trim();
      }
      if (titleText.startsWith("#") || (titleText.match(/#/g) || []).length >= 2) {
        // If even the group name has hashtags, extract topic words
        const m = titleText.match(/#([a-zA-Z0-9_-]+)\s+#([a-zA-Zа-яА-ЯёЁ0-9_-]+)/);
        if (m) {
          titleText = m[1].charAt(0).toUpperCase() + m[1].slice(1) + " (" + m[2] + ")";
        } else {
          titleText = "Задание";
        }
      }

      rawBlocks.push({
        node: n,
        nodeId: n.id,
        titleNode: titleNode,
        rawTitle: titleText.trim(),
        isTimestamp: isTimestamp,
        timestampTime: timestampTime,
        timestampDate: timestampDate,
        timestampShortDate: timestampShortDate,
        x: n.x,
        y: n.y,
        w: n.width,
        h: n.height
      });
    } else if (n.name && n.name.includes("Block Container Background")) {
      if (n.getPluginData && n.getPluginData("is_toc") === "true") continue;
      const bgX = n.x, bgY = n.y, bgW = n.width, bgH = n.height;
      const titleNode = children.find(c =>
        c.id !== n.id && !c.name.includes("Background") && !c.name.includes("В МЕНЮ") && !c.name.includes("ХЕШТЕГИ") && !c.name.includes("RESET") && !c.name.includes("СБРОС") && !c.name.includes("ОГЛАВЛЕНИЕ") &&
        !((c.characters || "").trim().startsWith("#")) &&
        c.x >= bgX - 40 && c.x <= bgX + bgW && c.y >= bgY - 30 && c.y <= bgY + 140
      );
      if (!titleNode) continue;
      let titleText = titleNode.characters || (titleNode.text ? titleNode.text.characters : titleNode.name);
      if (!titleText || titleText.includes("ОГЛАВЛЕНИЕ") || titleText.includes("переместиться") || titleText.startsWith("#")) continue;
      rawBlocks.push({
        node: n,
        nodeId: n.id,
        titleNode: titleNode,
        rawTitle: titleText.trim(),
        isTimestamp: false,
        timestampTime: "",
        timestampDate: "",
        timestampShortDate: "",
        x: bgX,
        y: bgY,
        w: bgW,
        h: bgH
      });
    }
  }

  // 3. Category definitions
  const CATEGORIES = [
    { num: 1, name: "КВИЗЫ", singular: "КВИЗ", icon: "🎯", bannerBg: "#1e3a8a", stroke: "#3b82f6", tagColor: "#93c5fd" },
    { num: 2, name: "ОТКРЫВАШКИ", singular: "ОТКРЫВАШКИ", icon: "🃏", bannerBg: "#831843", stroke: "#ec4899", tagColor: "#fbcfe8" },
    { num: 3, name: "ВИДЕО", singular: "ВИДЕО", icon: "🎬", bannerBg: "#581c87", stroke: "#a855f7", tagColor: "#e9d5ff" },
    { num: 4, name: "СЛОВАРИ", singular: "СЛОВАРИК", icon: "📋", bannerBg: "#064e3b", stroke: "#10b981", tagColor: "#a7f3d0" },
    { num: 5, name: "КАРТОЧКИ", singular: "КАРТОЧКИ", icon: "🗂", bannerBg: "#1e293b", stroke: "#64748b", tagColor: "#cbd5e1" },
    { num: 6, name: "УПРАЖНЕНИЯ", singular: "УПРАЖНЕНИЯ", icon: "✏️", bannerBg: "#14532d", stroke: "#22c55e", tagColor: "#bbf7d0" },
    { num: 7, name: "РАЗМИНКА", singular: "РАЗМИНКА", icon: "🏃", bannerBg: "#78350f", stroke: "#f59e0b", tagColor: "#fde68a" },
    { num: 8, name: "ТАЙМЛАЙН", singular: "ОТМЕТКА", icon: "🕒", bannerBg: "#0f766e", stroke: "#14b8a6", tagColor: "#99f6e4" },
    { num: 9, name: "УРОКИ", singular: "УРОК", icon: "🌟", bannerBg: "#312e81", stroke: "#6366f1", tagColor: "#c7d2fe" },
    { num: 10, name: "РАЗНОЕ", singular: "РАЗНОЕ", icon: "📌", bannerBg: "#334155", stroke: "#94a3b8", tagColor: "#e2e8f0" }
  ];

  function getCategory(block) {
    const role = (block.node.getPluginData ? block.node.getPluginData("role") : "") || "";
    const pCat = (block.node.getPluginData ? block.node.getPluginData("category") : "") || "";
    const isFullLesson = (block.node.getPluginData ? block.node.getPluginData("is_full_lesson") : "") === "true";
    const nodeNameUpper = (block.node.name || "").toUpperCase();
    const textUpper = (block.rawTitle + " " + (block.titleNode ? block.titleNode.name : "") + " " + block.node.name).toUpperCase();

    if (role === "full_lesson" || isFullLesson || nodeNameUpper.includes("🌟 УРОК") || nodeNameUpper.includes("УРОК:") || textUpper.includes("КОМПЛЕКСНЫЙ УРОК") || textUpper.includes("УРОК ЦЕЛИКОМ")) {
      return CATEGORIES[8]; // 9. УРОКИ
    }
    if (block.isTimestamp || role === "timestamp_block" || pCat.toLowerCase() === "таймлайн" || nodeNameUpper.includes("ОТМЕТКА ВРЕМЕНИ") || textUpper.includes("TIMESTAMP") || textUpper.includes("ВРЕМЯ УРОКА") || nodeNameUpper.includes("ТАЙМЛАЙН")) {
      return CATEGORIES[7]; // 8. ТАЙМЛАЙН
    }
    if (textUpper.includes("QUIZ") || textUpper.includes("КВИЗ") || textUpper.includes("QUESTION") || textUpper.includes("PREPOSITIONS") || textUpper.includes("ПРЕДЛОГИ") || textUpper.includes("VERBS")) {
      return CATEGORIES[0]; // 1. КВИЗЫ
    }
    if (textUpper.includes("FLIP") || textUpper.includes("REVEAL") || textUpper.includes("ОТКРЫВАШКИ") || textUpper.includes("PEEK-A-BOO") || textUpper.includes("PEEKABOO") || textUpper.includes("CAT") || textUpper.includes("КОТИК") || textUpper.includes("HOBBIES")) {
      return CATEGORIES[1]; // 2. ОТКРЫВАШКИ
    }
    if (textUpper.includes("VIDEO") || textUpper.includes("ВИДЕО") || textUpper.includes("YOUTUBE")) {
      return CATEGORIES[2]; // 3. ВИДЕО
    }
    if (textUpper.includes("VOCABULARY") || textUpper.includes("СЛОВАРИК") || textUpper.includes("СЛОВАРЬ") || textUpper.includes("TABLE") || textUpper.includes("ТАБЛИЦА") || textUpper.includes("PRONOUNS")) {
      return CATEGORIES[3]; // 4. СЛОВАРИ
    }
    if (textUpper.includes("FLASHCARD") || textUpper.includes("ФЛЕШКАРТ") || textUpper.includes("КАРТОЧКИ")) {
      return CATEGORIES[4]; // 5. КАРТОЧКИ
    }
    if (textUpper.includes("FILL") || textUpper.includes("BLANKS") || textUpper.includes("ПРОПУСК") || textUpper.includes("УПРАЖНЕНИ")) {
      return CATEGORIES[5]; // 6. УПРАЖНЕНИЯ
    }
    if (textUpper.includes("WARMUP") || textUpper.includes("WARM-UP") || textUpper.includes("РАЗМИНКА") || textUpper.includes("SPEAKING")) {
      return CATEGORIES[6]; // 7. РАЗМИНКА
    }
    return CATEGORIES[9]; // 10. РАЗНОЕ
  }

  function cleanBaseTitle(raw) {
    let cur = (raw || "").trim();
    cur = cur.replace(/\(Interactive Block\)/gi, "").trim();
    cur = cur.replace(/^🕒\s*/, "").trim();
    // Strip leading emojis with number code e.g. "🌟 1.2. " -> "🌟 "
    cur = cur.replace(/^([^\w\s\dа-яА-ЯёЁ]+)\s*\d+(\.\d+)?[\.\s\-:]+\s*/u, "$1 ");
    cur = cur.replace(/^\d+(\.\d+)?[\.\s\-:]+\s*/gi, "").trim();
    // Strip any trailing ellipsis dots so titles are never cut off
    cur = cur.replace(/\.{2,}$/, "").replace(/…$/, "").trim();
    return cur || "Задание";
  }

  const categorized = rawBlocks.map(b => {
    const cat = getCategory(b);
    const cleanTitle = cleanBaseTitle(b.rawTitle);
    return {
      ...b,
      category: cat,
      cleanTitle: cleanTitle,
      isTimestamp: b.isTimestamp || (cat.num === 8)
    };
  });

  // 4. Smart Numbering with Gap-Filling (Auto + Manual override)
  const blocksByCategory = {};
  for (const b of categorized) {
    const cNum = b.category.num;
    if (!blocksByCategory[cNum]) blocksByCategory[cNum] = [];
    blocksByCategory[cNum].push(b);
  }

  for (const cNum in blocksByCategory) {
    const list = blocksByCategory[cNum];
    const occupiedNumbers = new Map();
    const unassignedBlocks = [];

    for (const item of list) {
      let code = "";
      if (item.node.getPluginData) {
        code = item.node.getPluginData("block_code") || "";
      }
      if (!code && item.titleNode && item.titleNode.getPluginData) {
        code = item.titleNode.getPluginData("block_code") || "";
      }
      if (!code) {
        const m = item.rawTitle.match(new RegExp(`^${cNum}\\.(\\d+)`));
        if (m) code = `${cNum}.${m[1]}`;
      }

      if (code && code.startsWith(`${cNum}.`)) {
        const sub = parseInt(code.split(".")[1], 10);
        if (!isNaN(sub) && sub > 0 && !occupiedNumbers.has(sub)) {
          occupiedNumbers.set(sub, item);
          item.itemIndex = sub;
          item.numberCode = `${cNum}.${sub}`;
          continue;
        }
      }
      unassignedBlocks.push(item);
    }

    // Sort unassigned blocks by coordinates (Y then X)
    unassignedBlocks.sort((a, b) => a.y - b.y || a.x - b.x);

    // Fill missing gaps
    let candidateIndex = 1;
    for (const item of unassignedBlocks) {
      while (occupiedNumbers.has(candidateIndex)) {
        candidateIndex++;
      }
      occupiedNumbers.set(candidateIndex, item);
      item.itemIndex = candidateIndex;
      item.numberCode = `${cNum}.${candidateIndex}`;
      candidateIndex++;
    }

    // Sort list by itemIndex
    list.sort((a, b) => a.itemIndex - b.itemIndex);

    // Update nodes
    for (const item of list) {
      const isTimeline = (String(cNum) === "8" || item.isTimestamp);
      item.fullDisplayTitle = isTimeline ? item.cleanTitle : `${item.numberCode}. ${item.cleanTitle}`;
      item.colCardTitle = item.cleanTitle;

      if (item.node.setPluginData) {
        if (!isTimeline) {
          item.node.setPluginData("block_code", item.numberCode);
        }
        item.node.setPluginData("category_num", String(cNum));
        if (!item.node.getPluginData("created_at")) {
          item.node.setPluginData("created_at", String(Date.now()));
        }
      }

      if (item.node.type === "GROUP" || item.node.type === "SECTION") {
        if (item.node.getPluginData && item.node.getPluginData("role") === "timestamp_block") {
          item.node.name = `🕒 ${item.cleanTitle}`;
        } else {
          item.node.name = `${item.fullDisplayTitle} (Interactive Block)`;
        }
      }

      if (item.titleNode && (!item.node.getPluginData || item.node.getPluginData("role") !== "timestamp_block")) {
        try {
          const rawFn = item.titleNode.text ? item.titleNode.text.fontName : item.titleNode.fontName;
          if (rawFn && rawFn !== figma.mixed) {
            await figma.loadFontAsync({ family: rawFn.family, style: rawFn.style });
          }
          const bannerText = `${item.numberCode}. ${item.cleanTitle}`;
          if (item.titleNode.text) {
            item.titleNode.text.characters = bannerText;
          } else if (typeof item.titleNode.characters === "string") {
            item.titleNode.characters = bannerText;
          }
          item.titleNode.name = bannerText;
          item.titleNode.setPluginData("role", "block_title");
          item.titleNode.setPluginData("block_code", item.numberCode);
        } catch (e) { }
      }
    }
  }

  // Helper: Format creation timestamp
  function formatCreatedAt(node) {
    let ts = null;
    if (node && node.getPluginData) {
      ts = node.getPluginData("created_at");
    }
    const d = ts ? new Date(Number(ts)) : new Date();
    const months = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
    const day = d.getDate();
    const mon = months[d.getMonth()] || "";
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${day} ${mon}, ${hh}:${mm}`;
  }

  // 5. Build Column Layout (ONLY categories with existing blocks)
  // No abbreviations: all words wrap to new lines completely
  const categoryGroups = [];
  for (const cat of CATEGORIES) {
    const items = blocksByCategory[cat.num];
    if (items && items.length > 0) {
      for (const item of items) {
        if (cat.num === 8 || item.isTimestamp) {
          // ТАЙМЛАЙН: Single-line ultra-compact format with full time and full date!
          const timeStr = item.timestampTime || (formatCreatedAt(item.node).split(", ")[1] || "12:00");
          let dateStr = item.timestampDate || item.timestampShortDate || (formatCreatedAt(item.node).split(", ")[0] || "");
          dateStr = dateStr.replace(/^📅\s*/, "").trim();
          item.cardText = dateStr ? `🕒 ${timeStr}   📅 ${dateStr}` : `🕒 ${timeStr}`;
          item.estHeight = 38;
        } else {
          // Regular block: Full unabbreviated title!
          let cardTitle = item.cleanTitle;
          if (cardTitle.includes("•")) {
            cardTitle = cardTitle.split("•").map((s, idx) => idx === 0 ? s.trim() : "\n• " + s.trim()).join("").trim();
          }
          item.cardText = cardTitle;
          item.estHeight = cardTitle.length > 28 ? 56 : 42;
        }
      }
      categoryGroups.push({
        category: cat,
        items: items
      });
    }
  }

  // Dimensions: 420px column width for spacious readable layout
  const numCols = Math.max(1, categoryGroups.length);
  const colW = 420;
  const colGap = 22;
  const padX = 32;
  const padY = 28;
  const contentW = numCols * colW + (numCols - 1) * colGap;
  const tocW = contentW + padX * 2;

  let maxColInnerH = 0;
  for (const grp of categoryGroups) {
    let colH = 0;
    for (const itm of grp.items) {
      colH += (itm.estHeight || 42) + 8;
    }
    if (colH > maxColInnerH) maxColInnerH = colH;
  }
  const colBoxH = Math.max(120, maxColInnerH + 20);

  const headerH = 64;
  const colTitleH = 46;
  const tagsH = 36;
  const totalContentH = headerH + 18 + colTitleH + 10 + colBoxH + 16 + tagsH;
  const containerH = totalContentH + padY * 2;

  const minActivityX = categorized.length > 0 ? Math.min(...categorized.map(b => b.x)) : 0;
  const minActivityY = categorized.length > 0 ? Math.min(...categorized.map(b => b.y)) : 0;
  const baseX = (defaultBaseX && Math.abs(defaultBaseX - minActivityX) > 200) ? defaultBaseX : (minActivityX - tocW - 120);
  const baseY = defaultBaseY || Math.max(-500, minActivityY);

  const createdNodes = [];

  // 0. Background Container (Universal RectangleNode with smooth border)
  const bg = figma.createRectangle();
  bg.resize(tocW, containerH);
  bg.x = baseX - padX;
  bg.y = baseY - padY;
  bg.cornerRadius = 24;
  bg.fills = [{ type: "SOLID", color: hexToRgb("#f8fafc") }];
  bg.strokes = [{ type: "SOLID", color: hexToRgb("#cbd5e1") }];
  bg.strokeWeight = 2.5;
  bg.name = "🖼️ Block Container Background";
  bg.setPluginData("role", "block_container");
  bg.setPluginData("is_toc", "true");
  bg.locked = true;
  figma.currentPage.appendChild(bg);
  createdNodes.push(bg);

  // 1. Header Banner: "📑 ОГЛАВЛЕНИЕ ДОСКИ"
  const titleBannerBg = figma.createRectangle();
  titleBannerBg.resize(contentW, headerH);
  titleBannerBg.x = baseX;
  titleBannerBg.y = baseY;
  titleBannerBg.cornerRadius = 14;
  titleBannerBg.fills = [{ type: "SOLID", color: hexToRgb("#ffffff") }];
  titleBannerBg.strokes = [{ type: "SOLID", color: hexToRgb("#cbd5e1") }];
  titleBannerBg.strokeWeight = 1.5;
  titleBannerBg.name = "TOC Header Banner";
  titleBannerBg.setPluginData("role", "toc_header");
  titleBannerBg.locked = true;
  figma.currentPage.appendChild(titleBannerBg);
  createdNodes.push(titleBannerBg);

  const titleBannerTxt = figma.createText();
  titleBannerTxt.fontName = { family: "Inter", style: "Bold" };
  titleBannerTxt.fontSize = 26;
  titleBannerTxt.characters = "📑 ОГЛАВЛЕНИЕ ДОСКИ";
  titleBannerTxt.fills = [{ type: "SOLID", color: hexToRgb("#0f172a") }];
  titleBannerTxt.textAlignHorizontal = "CENTER";
  titleBannerTxt.textAutoResize = "NONE";
  titleBannerTxt.resize(contentW, headerH);
  titleBannerTxt.x = baseX;
  titleBannerTxt.y = baseY + Math.round((headerH - 32) / 2);
  titleBannerTxt.locked = true;
  figma.currentPage.appendChild(titleBannerTxt);
  createdNodes.push(titleBannerTxt);

  // 2. Multi-Column Category Layout
  const columnsStartY = baseY + headerH + 18;
  let maxColBottomY = columnsStartY;

  for (let cIdx = 0; cIdx < categoryGroups.length; cIdx++) {
    const grp = categoryGroups[cIdx];
    const cat = grp.category;
    const isTimeline = (cat.num === 8);
    const colX = baseX + cIdx * (colW + colGap);

    // Column Header Banner
    const colHeaderBg = figma.createRectangle();
    colHeaderBg.resize(colW, colTitleH);
    colHeaderBg.x = colX;
    colHeaderBg.y = columnsStartY;
    colHeaderBg.cornerRadius = 12;
    colHeaderBg.fills = [{ type: "SOLID", color: hexToRgb(cat.bannerBg) }];
    colHeaderBg.strokes = [{ type: "SOLID", color: hexToRgb(cat.stroke) }];
    colHeaderBg.strokeWeight = 1.5;
    colHeaderBg.locked = true;
    figma.currentPage.appendChild(colHeaderBg);
    createdNodes.push(colHeaderBg);

    const colHeaderTxt = figma.createText();
    colHeaderTxt.fontName = { family: "Inter", style: "Bold" };
    colHeaderTxt.fontSize = 15;
    colHeaderTxt.characters = `${cat.icon}  ${cat.name}  (${grp.items.length})`;
    colHeaderTxt.fills = [{ type: "SOLID", color: hexToRgb("#ffffff") }];
    colHeaderTxt.textAlignHorizontal = "CENTER";
    colHeaderTxt.textAutoResize = "NONE";
    colHeaderTxt.resize(colW, colTitleH);
    colHeaderTxt.x = colX;
    colHeaderTxt.y = columnsStartY + Math.round((colTitleH - 18) / 2);
    colHeaderTxt.locked = true;
    figma.currentPage.appendChild(colHeaderTxt);
    createdNodes.push(colHeaderTxt);

    // Column Container Box (Soft grey iOS grouped container)
    const colBoxY = columnsStartY + colTitleH + 10;
    const colBox = figma.createRectangle();
    colBox.resize(colW, colBoxH);
    colBox.x = colX;
    colBox.y = colBoxY;
    colBox.cornerRadius = 16;
    colBox.fills = [{ type: "SOLID", color: hexToRgb("#f1f5f9") }];
    colBox.strokes = [{ type: "SOLID", color: hexToRgb("#e2e8f0") }];
    colBox.strokeWeight = 1.5;
    colBox.locked = true;
    figma.currentPage.appendChild(colBox);
    createdNodes.push(colBox);

    // Activity Cards inside Column
    let itemY = colBoxY + 12;
    const itemW = colW - 24; // 396px
    const itemX = colX + 12;

    for (const item of grp.items) {
      const targetNodeId = item.nodeId;

      if (isTimeline) {
        // ─── TIMELINE CARD (ULTRA-COMPACT, NO NUMBER BADGE, 100% FULL TEXT) ───
        const btnX = itemX;
        const btnW = itemW; // 396px full width!

        // Create TextNode first with textAutoResize = "HEIGHT" to get exact pixel height
        const txt = figma.createText();
        txt.fontName = { family: "Inter", style: "Medium" };
        txt.fontSize = 13;
        txt.characters = item.cardText;
        txt.fills = [{ type: "SOLID", color: hexToRgb("#0f172a") }];
        txt.textAlignHorizontal = "LEFT";
        try { txt.textTruncation = "DISABLED"; } catch (e) { }
        txt.x = btnX + 14;
        txt.textAutoResize = "HEIGHT";
        txt.resize(btnW - 38, 20); // 14px left, 24px right (chevron)
        figma.currentPage.appendChild(txt);

        const cardH = Math.max(38, Math.round(txt.height + 16));
        txt.y = itemY + Math.round((cardH - txt.height) / 2);

        // iOS white card background
        const cardBg = figma.createRectangle();
        cardBg.x = btnX;
        cardBg.y = itemY;
        cardBg.resize(btnW, cardH);
        cardBg.cornerRadius = 12;
        cardBg.fills = [{ type: "SOLID", color: hexToRgb("#ffffff") }];
        cardBg.strokes = [{ type: "SOLID", color: hexToRgb("#e2e8f0") }];
        cardBg.strokeWeight = 1.2;
        cardBg.name = item.cardText;
        cardBg.setPluginData("role", "toc_item");
        cardBg.setPluginData("target_id", targetNodeId);
        cardBg.setPluginData("target_title", item.cardText);
        figma.currentPage.appendChild(cardBg);

        // Ensure text is above background
        try { cardBg.parent.insertChild(cardBg.parent.children.indexOf(txt), cardBg); } catch (e) { }

        // Hyperlink on text
        try {
          txt.setRangeHyperlink(0, txt.characters.length, { type: "NODE", value: targetNodeId });
        } catch (e) { }
        txt.setPluginData("role", "toc_item");
        txt.setPluginData("target_id", targetNodeId);

        // iOS Chevron ›
        const chev = figma.createText();
        chev.fontName = { family: "Inter", style: "Bold" };
        chev.fontSize = 16;
        chev.characters = "›";
        chev.fills = [{ type: "SOLID", color: hexToRgb("#94a3b8") }];
        chev.textAlignHorizontal = "CENTER";
        chev.x = btnX + btnW - 18;
        chev.y = itemY + Math.round((cardH - 20) / 2);
        chev.locked = true;
        try { chev.setRangeHyperlink(0, 1, { type: "NODE", value: targetNodeId }); } catch (e) { }
        figma.currentPage.appendChild(chev);

        createdNodes.push(cardBg, txt, chev);
        itemY += cardH + 8;

      } else {
        // ─── REGULAR ACTIVITY CARD (SEPARATE NUMBER BADGE + FULL TITLE WITHOUT CUTS) ───
        const badgeW = 44;
        const gap = 8;
        const btnX = itemX + badgeW + gap;
        const btnW = itemW - badgeW - gap; // 344px

        // Create TextNode first with textAutoResize = "HEIGHT" to get exact pixel height
        const txt = figma.createText();
        txt.fontName = { family: "Inter", style: "Medium" };
        txt.fontSize = 13;
        txt.characters = item.cardText;
        txt.fills = [{ type: "SOLID", color: hexToRgb("#0f172a") }];
        txt.textAlignHorizontal = "LEFT";
        try { txt.textTruncation = "DISABLED"; } catch (e) { }
        txt.x = btnX + 14;
        txt.textAutoResize = "HEIGHT";
        txt.resize(btnW - 36, 20); // 14px left, 22px right (chevron)
        figma.currentPage.appendChild(txt);

        const cardH = Math.max(42, Math.round(txt.height + 18));
        txt.y = itemY + Math.round((cardH - txt.height) / 2);

        // 1. Separate Number Badge on Left
        const badgeH = Math.min(30, cardH - 6);
        const badgeY = itemY + (cardH > 48 ? 6 : Math.round((cardH - badgeH) / 2));

        const badgeBg = figma.createRectangle();
        badgeBg.x = itemX;
        badgeBg.y = badgeY;
        badgeBg.resize(badgeW, badgeH);
        badgeBg.cornerRadius = 10;
        badgeBg.fills = [{ type: "SOLID", color: hexToRgb("#ffffff") }];
        badgeBg.strokes = [{ type: "SOLID", color: hexToRgb(cat.stroke) }];
        badgeBg.strokeWeight = 1.5;
        badgeBg.setPluginData("role", "toc_item");
        badgeBg.setPluginData("target_id", targetNodeId);
        figma.currentPage.appendChild(badgeBg);

        const badgeTxt = figma.createText();
        badgeTxt.fontName = { family: "Inter", style: "Bold" };
        badgeTxt.fontSize = 12;
        badgeTxt.characters = item.numberCode;
        badgeTxt.fills = [{ type: "SOLID", color: hexToRgb(cat.stroke) }];
        badgeTxt.textAlignHorizontal = "CENTER";
        badgeTxt.textAutoResize = "NONE";
        badgeTxt.resize(badgeW, badgeH);
        badgeTxt.x = itemX;
        badgeTxt.y = badgeY + Math.round((badgeH - 16) / 2);
        badgeTxt.setPluginData("role", "toc_item");
        badgeTxt.setPluginData("target_id", targetNodeId);
        try { badgeTxt.setRangeHyperlink(0, badgeTxt.characters.length, { type: "NODE", value: targetNodeId }); } catch (e) { }
        figma.currentPage.appendChild(badgeTxt);

        // 2. iOS white button background
        const cardBg = figma.createRectangle();
        cardBg.x = btnX;
        cardBg.y = itemY;
        cardBg.resize(btnW, cardH);
        cardBg.cornerRadius = 12;
        cardBg.fills = [{ type: "SOLID", color: hexToRgb("#ffffff") }];
        cardBg.strokes = [{ type: "SOLID", color: hexToRgb("#e2e8f0") }];
        cardBg.strokeWeight = 1.2;
        cardBg.name = item.fullDisplayTitle;
        cardBg.setPluginData("role", "toc_item");
        cardBg.setPluginData("target_id", targetNodeId);
        cardBg.setPluginData("target_title", item.fullDisplayTitle);
        cardBg.setPluginData("block_code", item.numberCode);
        figma.currentPage.appendChild(cardBg);

        // Ensure text is above background
        try { cardBg.parent.insertChild(cardBg.parent.children.indexOf(txt), cardBg); } catch (e) { }

        // Hyperlink on text
        try { txt.setRangeHyperlink(0, txt.characters.length, { type: "NODE", value: targetNodeId }); } catch (e) { }
        txt.setPluginData("role", "toc_item");
        txt.setPluginData("target_id", targetNodeId);

        // 3. iOS Chevron ›
        const chev = figma.createText();
        chev.fontName = { family: "Inter", style: "Bold" };
        chev.fontSize = 16;
        chev.characters = "›";
        chev.fills = [{ type: "SOLID", color: hexToRgb("#94a3b8") }];
        chev.textAlignHorizontal = "CENTER";
        chev.x = btnX + btnW - 18;
        chev.y = itemY + Math.round((cardH - 20) / 2);
        chev.locked = true;
        try { chev.setRangeHyperlink(0, 1, { type: "NODE", value: targetNodeId }); } catch (e) { }
        figma.currentPage.appendChild(chev);

        createdNodes.push(badgeBg, badgeTxt, cardBg, txt, chev);
        itemY += cardH + 8;
      }
    }

    // Auto-fit column box to actual items
    const actualColInnerH = itemY - (colBoxY + 12);
    const finalColBoxH = Math.max(colBoxH, actualColInnerH + 16);
    colBox.resize(colW, finalColBoxH);
    if (colBoxY + finalColBoxH > maxColBottomY) {
      maxColBottomY = colBoxY + finalColBoxH;
    }
  }

  // 3. Hashtags Footer
  const footerY = maxColBottomY + 16;
  const tagsBg = figma.createRectangle();
  tagsBg.resize(contentW, tagsH);
  tagsBg.x = baseX;
  tagsBg.y = footerY;
  tagsBg.cornerRadius = 8;
  tagsBg.fills = [{ type: "SOLID", color: hexToRgb("#f1f5f9") }];
  tagsBg.strokes = [{ type: "SOLID", color: hexToRgb("#e2e8f0") }];
  tagsBg.strokeWeight = 1;
  tagsBg.setPluginData("role", "hashtags_footer");
  tagsBg.locked = true;
  figma.currentPage.appendChild(tagsBg);
  createdNodes.push(tagsBg);

  const tagsTxt = figma.createText();
  tagsTxt.fontName = { family: "Inter", style: "Regular" };
  tagsTxt.fontSize = 11;
  tagsTxt.characters = "🏷️ #оглавление #содержание #навигация #меню #dashboard #timeline #таймлайн";
  tagsTxt.fills = [{ type: "SOLID", color: hexToRgb("#64748b") }];
  tagsTxt.textAlignHorizontal = "CENTER";
  tagsTxt.textAutoResize = "NONE";
  tagsTxt.resize(contentW, tagsH);
  tagsTxt.x = baseX;
  tagsTxt.y = footerY + Math.round((tagsH - 15) / 2);
  tagsTxt.locked = true;
  figma.currentPage.appendChild(tagsTxt);
  createdNodes.push(tagsTxt);

  // Resize overall background container to exact fit
  const finalContainerH = (footerY + tagsH + padY) - (baseY - padY);
  bg.resize(tocW, finalContainerH);

  // Move bg to lowest layer
  try {
    const bgIdx = createdNodes.indexOf(bg);
    if (bgIdx > 0) {
      createdNodes.splice(bgIdx, 1);
      createdNodes.unshift(bg);
    }
  } catch (e) { }

  // Group all TOC elements together and lock firmly on canvas!
  let tocGroup;
  try {
    tocGroup = figma.group(createdNodes, figma.currentPage);
    tocGroup.name = "📑 ОГЛАВЛЕНИЕ ДОСКИ (Table of Contents)";
    tocGroup.setPluginData("role", "table_of_contents");
    tocGroup.insertChild(0, bg);
    tocGroup.locked = true; // Lock TOC group
  } catch (e) { }

  figma.notify(`📑 Оглавление обновлено! Колонок: ${categoryGroups.length}, Заданий: ${categorized.length}`, { timeout: 2500 });

  return {
    success: true,
    columnsCount: categoryGroups.length,
    totalBlocks: categorized.length,
    categories: categoryGroups.map(g => ({
      name: g.category.name,
      count: g.items.length
    }))
  };
}

// Helper: Check if node is part of Table of Contents block
function isInsideTOC(node) {
  let curr = node;
  while (curr && curr !== figma.currentPage) {
    const r = (curr.getPluginData ? curr.getPluginData("role") : "") || "";
    if (r === "table_of_contents" || r === "toc_header" || (curr.getPluginData && curr.getPluginData("is_toc") === "true")) return true;
    const n = curr.name || "";
    if (n.includes("ОГЛАВЛЕНИЕ ДОСКИ") || n.includes("Table of Contents")) return true;
    curr = curr.parent;
  }
  return false;
}


