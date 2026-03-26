// 测试文件夹选择：
// 1. npm start 启动 Electron
// 2. 点击侧边栏 "选择项目文件夹"
// 3. 选择一个文件夹（如桌面上的某个项目）
// 4. 新建对话，发送 "读一下当前目录有什么文件"
// 5. Agent 应该调用 Read 或 Bash 工具，返回该文件夹下的文件列表
const { app, BrowserWindow, dialog, ipcMain } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");

let mainWindow = null;
let backendProcess = null;
const BACKEND_PORT = 8000;
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`;

ipcMain.handle("select-folder", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openDirectory"],
    title: "选择项目文件夹",
  });
  if (result.canceled || !result.filePaths.length) return null;
  return result.filePaths[0];
});

ipcMain.handle("get-cwd", () => {
  return process.cwd();
});

function getBackendPath() {
  if (!app.isPackaged) return null;
  return path.join(process.resourcesPath, "backend", "agent-studio-backend.exe");
}

function getFrontendPath() {
  if (!app.isPackaged) return null;
  return path.join(process.resourcesPath, "frontend", "index.html");
}

function startBackend() {
  const exePath = getBackendPath();
  if (!exePath) {
    console.log("Dev mode: skip backend spawn, expecting manual start");
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    console.log("Starting backend:", exePath);
    backendProcess = spawn(exePath, [], {
      cwd: path.dirname(exePath),
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, API_PORT: String(BACKEND_PORT) },
    });
    backendProcess.stdout.on("data", (data) => {
      console.log(`[backend] ${data.toString().trim()}`);
    });
    backendProcess.stderr.on("data", (data) => {
      console.error(`[backend] ${data.toString().trim()}`);
    });
    backendProcess.on("error", (err) => {
      console.error("Backend failed to start:", err);
      reject(err);
    });
    backendProcess.on("exit", (code) => {
      console.log(`Backend exited with code ${code}`);
      backendProcess = null;
    });
    waitForBackend(30000).then(resolve).catch(reject);
  });
}

function waitForBackend(timeoutMs) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const check = () => {
      if (Date.now() - start > timeoutMs) return reject(new Error("Backend startup timeout"));
      http
        .get(`${BACKEND_URL}/health`, (res) => {
          if (res.statusCode === 200) return resolve();
          setTimeout(check, 500);
        })
        .on("error", () => setTimeout(check, 500));
    };
    check();
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: "#000000",
    title: "Agent Studio",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });
  const frontendPath = getFrontendPath();
  if (frontendPath) {
    mainWindow.loadFile(frontendPath);
  } else {
    mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools();
  }
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  try {
    await startBackend();
    createWindow();
  } catch (err) {
    dialog.showErrorBox("启动失败", `后端启动失败: ${err.message}`);
    app.quit();
  }
});

app.on("window-all-closed", () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
  app.quit();
});

app.on("before-quit", () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});
