import { Router, type IRouter } from "express";
import multer from "multer";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";
import os from "os";

const router: IRouter = Router();

const upload = multer({
  dest: os.tmpdir(),
  limits: { fileSize: 50 * 1024 * 1024, files: 1000 },
  fileFilter: (_req, file, cb) => {
    if (file.mimetype === "application/pdf" || file.originalname.endsWith(".pdf")) {
      cb(null, true);
    } else {
      cb(new Error("Only PDF files are allowed"));
    }
  },
});

router.post("/process-pdfs", upload.array("pdfs", 1000), async (req, res) => {
  const files = req.files as Express.Multer.File[];

  if (!files || files.length === 0) {
    res.status(400).json({ error: "No PDF files uploaded" });
    return;
  }

  const outputPath = path.join(os.tmpdir(), `reembolso_${Date.now()}.xlsx`);
  const pdfPaths = files.map((f) => f.path);
  const includeZeros = req.body.includeZeros === "true";

  const scriptPath = path.resolve(process.cwd(), "../../streamlit-app/process_pdfs.py");

  const args = [...pdfPaths, "--output", outputPath];
  if (includeZeros) args.push("--include-zeros");

  try {
    const result = await new Promise<{ stdout: string; stderr: string; code: number }>(
      (resolve) => {
        const proc = spawn("python3", [scriptPath, ...args]);
        let stdout = "";
        let stderr = "";
        proc.stdout.on("data", (d) => (stdout += d.toString()));
        proc.stderr.on("data", (d) => (stderr += d.toString()));
        proc.on("close", (code) => resolve({ stdout, stderr, code: code ?? 1 }));
      }
    );

    pdfPaths.forEach((p) => {
      try { fs.unlinkSync(p); } catch {}
    });

    if (result.code !== 0) {
      let errorMsg = "PDF processing failed";
      try {
        const parsed = JSON.parse(result.stdout);
        errorMsg = parsed.error || errorMsg;
      } catch {}
      res.status(500).json({ error: errorMsg, details: result.stderr });
      return;
    }

    let processingResult: { success: boolean; rows: number; files: number; errors: string[] } | null = null;
    try {
      processingResult = JSON.parse(result.stdout);
    } catch {}

    if (!processingResult?.success) {
      res.status(500).json({ error: "Processing returned no data" });
      return;
    }

    if (!fs.existsSync(outputPath)) {
      res.status(500).json({ error: "Output file was not created" });
      return;
    }

    res.setHeader("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    res.setHeader("Content-Disposition", "attachment; filename=reembolso_consolidado.xlsx");
    res.setHeader("X-Rows", String(processingResult.rows));
    res.setHeader("X-Files", String(processingResult.files));
    res.setHeader("X-Errors", JSON.stringify(processingResult.errors));

    const stream = fs.createReadStream(outputPath);
    stream.pipe(res);
    stream.on("end", () => {
      try { fs.unlinkSync(outputPath); } catch {}
    });
  } catch (err) {
    pdfPaths.forEach((p) => { try { fs.unlinkSync(p); } catch {} });
    res.status(500).json({ error: String(err) });
  }
});

export default router;
