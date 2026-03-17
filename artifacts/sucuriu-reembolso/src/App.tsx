import { useState, useCallback, useRef } from "react";

interface ProcessingResult {
  rows: number;
  files: number;
  errors: string[];
}

type Status = "idle" | "processing" | "done" | "error";

export default function App() {
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<ProcessingResult | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [includeZeros, setIncludeZeros] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback((newFiles: FileList | File[]) => {
    const pdfs = Array.from(newFiles).filter(
      (f) => f.type === "application/pdf" || f.name.endsWith(".pdf")
    );
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name + f.size));
      return [...prev, ...pdfs.filter((f) => !existing.has(f.name + f.size))];
    });
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      addFiles(e.dataTransfer.files);
    },
    [addFiles]
  );

  const removeFile = (idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const reset = () => {
    setFiles([]);
    setStatus("idle");
    setProgress(0);
    setResult(null);
    setErrorMsg("");
    if (downloadUrl) URL.revokeObjectURL(downloadUrl);
    setDownloadUrl(null);
  };

  const processFiles = async () => {
    if (!files.length) return;
    setStatus("processing");
    setProgress(0);
    setResult(null);
    setErrorMsg("");

    const formData = new FormData();
    files.forEach((f) => formData.append("pdfs", f));
    formData.append("includeZeros", String(includeZeros));

    try {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/process-pdfs");
      xhr.responseType = "arraybuffer";

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          setProgress(Math.round((e.loaded / e.total) * 60));
        }
      };

      xhr.onprogress = () => setProgress(80);

      xhr.onload = () => {
        if (xhr.status === 200) {
          const rows = parseInt(xhr.getResponseHeader("X-Rows") || "0");
          const fileCount = parseInt(xhr.getResponseHeader("X-Files") || "0");
          const errorsHeader = xhr.getResponseHeader("X-Errors") || "[]";
          let errors: string[] = [];
          try { errors = JSON.parse(errorsHeader); } catch {}

          const blob = new Blob([xhr.response], {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          });
          const url = URL.createObjectURL(blob);
          setDownloadUrl(url);
          setResult({ rows, files: fileCount, errors });
          setStatus("done");
          setProgress(100);
        } else {
          let errMsg = `Erro ${xhr.status}`;
          try {
            const text = new TextDecoder().decode(new Uint8Array(xhr.response as ArrayBuffer));
            const body = JSON.parse(text);
            errMsg = body.error || errMsg;
          } catch {}
          setErrorMsg(errMsg);
          setStatus("error");
        }
      };

      xhr.onerror = () => {
        setErrorMsg("Falha na conexão com o servidor. Verifique se o serviço está rodando.");
        setStatus("error");
      };

      xhr.send(formData);
    } catch (err) {
      setErrorMsg(String(err));
      setStatus("error");
    }
  };

  return (
    <div className="min-h-screen py-10 px-4" style={{ background: "linear-gradient(135deg, #0f2c4a 0%, #0d4a4a 100%)" }}>
      <div className="max-w-2xl mx-auto space-y-5">

        {/* Header */}
        <div className="text-center space-y-2 pb-2">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl mb-2"
            style={{ background: "linear-gradient(135deg, #0ea5e9, #14b8a6)" }}>
            <span className="text-2xl">📄</span>
          </div>
          <h1 className="text-3xl font-bold text-white tracking-tight">
            Consolidador de Reembolso
          </h1>
          <p className="text-sm" style={{ color: "#7dd3d8" }}>
            Projeto Sucuriú — faça upload dos PDFs e baixe a planilha consolidada
          </p>
        </div>

        {status === "idle" || status === "error" ? (
          <>
            {/* Drop zone */}
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              onClick={() => inputRef.current?.click()}
              className="rounded-2xl p-10 text-center cursor-pointer transition-all duration-200 border-2 border-dashed"
              style={{
                background: dragging ? "rgba(20,184,166,0.12)" : "rgba(255,255,255,0.05)",
                borderColor: dragging ? "#14b8a6" : "rgba(125,211,216,0.35)",
                backdropFilter: "blur(4px)",
              }}
            >
              <input
                ref={inputRef}
                type="file"
                accept=".pdf,application/pdf"
                multiple
                className="hidden"
                onChange={(e) => e.target.files && addFiles(e.target.files)}
              />
              <div className="text-5xl mb-4">📂</div>
              <p className="font-semibold text-white text-lg">
                Arraste os PDFs aqui ou clique para selecionar
              </p>
              <p className="text-sm mt-1" style={{ color: "#7dd3d8" }}>
                Suporta múltiplos arquivos — até 1.000 PDFs por vez
              </p>
            </div>

            {/* File list */}
            {files.length > 0 && (
              <div className="rounded-2xl overflow-hidden border" style={{ borderColor: "rgba(125,211,216,0.2)", background: "rgba(255,255,255,0.05)" }}>
                <div className="px-4 py-3 flex justify-between items-center border-b" style={{ borderColor: "rgba(125,211,216,0.15)" }}>
                  <span className="text-sm font-semibold text-white">
                    {files.length} arquivo{files.length !== 1 ? "s" : ""} selecionado{files.length !== 1 ? "s" : ""}
                  </span>
                  <button
                    onClick={(e) => { e.stopPropagation(); setFiles([]); }}
                    className="text-xs transition-colors"
                    style={{ color: "#7dd3d8" }}
                    onMouseOver={(e) => (e.currentTarget.style.color = "#f87171")}
                    onMouseOut={(e) => (e.currentTarget.style.color = "#7dd3d8")}
                  >
                    Remover todos
                  </button>
                </div>
                <ul className="max-h-48 overflow-y-auto divide-y" style={{ borderColor: "rgba(125,211,216,0.1)" }}>
                  {files.map((f, i) => (
                    <li key={i} className="flex items-center justify-between px-4 py-2">
                      <span className="text-sm truncate max-w-xs" style={{ color: "#cbd5e1" }}>{f.name}</span>
                      <button
                        onClick={() => removeFile(i)}
                        className="ml-2 flex-shrink-0 text-lg leading-none transition-colors"
                        style={{ color: "rgba(125,211,216,0.4)" }}
                        onMouseOver={(e) => (e.currentTarget.style.color = "#f87171")}
                        onMouseOut={(e) => (e.currentTarget.style.color = "rgba(125,211,216,0.4)")}
                      >
                        ✕
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Options */}
            <div className="flex items-center gap-3 rounded-2xl px-4 py-3 border" style={{ background: "rgba(255,255,255,0.05)", borderColor: "rgba(125,211,216,0.2)" }}>
              <input
                id="includeZeros"
                type="checkbox"
                checked={includeZeros}
                onChange={(e) => setIncludeZeros(e.target.checked)}
                className="w-4 h-4 rounded"
                style={{ accentColor: "#14b8a6" }}
              />
              <label htmlFor="includeZeros" className="text-sm cursor-pointer select-none" style={{ color: "#7dd3d8" }}>
                Incluir linhas com Qtd = 0 (itens sem consumo)
              </label>
            </div>

            {/* Error message */}
            {status === "error" && (
              <div className="rounded-2xl px-4 py-3 border" style={{ background: "rgba(239,68,68,0.1)", borderColor: "rgba(239,68,68,0.3)" }}>
                <p className="text-sm font-medium" style={{ color: "#fca5a5" }}>❌ Erro ao processar</p>
                <p className="text-sm mt-1" style={{ color: "#fca5a5" }}>{errorMsg}</p>
              </div>
            )}

            {/* Process button */}
            <button
              onClick={processFiles}
              disabled={files.length === 0}
              className="w-full font-semibold py-3.5 rounded-2xl text-sm transition-all duration-200"
              style={{
                background: files.length === 0
                  ? "rgba(255,255,255,0.1)"
                  : "linear-gradient(135deg, #0ea5e9, #14b8a6)",
                color: files.length === 0 ? "rgba(255,255,255,0.3)" : "white",
                cursor: files.length === 0 ? "not-allowed" : "pointer",
                boxShadow: files.length === 0 ? "none" : "0 4px 20px rgba(14,165,233,0.35)",
              }}
            >
              🚀 Processar e Gerar Planilha
            </button>
          </>
        ) : status === "processing" ? (
          /* Processing state */
          <div className="rounded-2xl p-10 text-center space-y-5 border" style={{ background: "rgba(255,255,255,0.05)", borderColor: "rgba(125,211,216,0.2)" }}>
            <div className="text-5xl">⚙️</div>
            <div>
              <p className="text-white font-medium text-lg">
                Processando {files.length} arquivo{files.length !== 1 ? "s" : ""}...
              </p>
              <p className="text-sm mt-1" style={{ color: "#7dd3d8" }}>
                Extraindo dados e gerando planilha
              </p>
            </div>
            <div className="w-full rounded-full h-2.5 overflow-hidden" style={{ background: "rgba(255,255,255,0.1)" }}>
              <div
                className="h-2.5 rounded-full transition-all duration-500"
                style={{
                  width: `${progress}%`,
                  background: "linear-gradient(90deg, #0ea5e9, #14b8a6)",
                }}
              />
            </div>
            <p className="text-sm font-mono" style={{ color: "#7dd3d8" }}>{progress}%</p>
          </div>
        ) : (
          /* Done state */
          <div className="space-y-4">
            <div className="rounded-2xl p-8 text-center space-y-3 border" style={{ background: "rgba(20,184,166,0.1)", borderColor: "rgba(20,184,166,0.3)" }}>
              <div className="text-5xl">✅</div>
              <p className="text-white font-semibold text-xl">Planilha gerada com sucesso!</p>
              <div className="flex justify-center gap-6 text-sm" style={{ color: "#5eead4" }}>
                <span>📁 {result?.files} arquivo{result?.files !== 1 ? "s" : ""} processado{result?.files !== 1 ? "s" : ""}</span>
                <span>📊 {result?.rows} linhas extraídas</span>
              </div>
            </div>

            {downloadUrl && (
              <a
                href={downloadUrl}
                download="reembolso_consolidado.xlsx"
                className="flex items-center justify-center gap-2 w-full font-semibold py-3.5 rounded-2xl text-sm text-white transition-all duration-200"
                style={{
                  background: "linear-gradient(135deg, #0ea5e9, #14b8a6)",
                  boxShadow: "0 4px 20px rgba(14,165,233,0.35)",
                }}
              >
                ⬇️ Baixar reembolso_consolidado.xlsx
              </a>
            )}

            {result?.errors && result.errors.length > 0 && (
              <div className="rounded-2xl overflow-hidden border" style={{ background: "rgba(245,158,11,0.08)", borderColor: "rgba(245,158,11,0.25)" }}>
                <div className="px-4 py-3 border-b" style={{ borderColor: "rgba(245,158,11,0.15)" }}>
                  <p className="text-sm font-semibold" style={{ color: "#fcd34d" }}>
                    ⚠️ {result.errors.length} aviso{result.errors.length !== 1 ? "s" : ""} durante o processamento
                  </p>
                </div>
                <ul className="max-h-40 overflow-y-auto divide-y" style={{ borderColor: "rgba(245,158,11,0.1)" }}>
                  {result.errors.map((e, i) => (
                    <li key={i} className="px-4 py-2 text-xs" style={{ color: "#fcd34d" }}>{e}</li>
                  ))}
                </ul>
              </div>
            )}

            <button
              onClick={reset}
              className="w-full font-medium py-3 rounded-2xl text-sm transition-all duration-200 border"
              style={{
                background: "rgba(255,255,255,0.06)",
                color: "#7dd3d8",
                borderColor: "rgba(125,211,216,0.2)",
              }}
            >
              🔄 Processar mais arquivos
            </button>
          </div>
        )}

        <p className="text-center text-xs pb-4" style={{ color: "rgba(125,211,216,0.4)" }}>
          Projeto Sucuriú · Consolidador de Reembolso de Despesas
        </p>
      </div>
    </div>
  );
}
