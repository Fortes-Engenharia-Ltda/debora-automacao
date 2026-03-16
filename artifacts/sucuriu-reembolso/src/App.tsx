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
            const body = JSON.parse(xhr.responseText);
            errMsg = body.error || errMsg;
          } catch {}
          setErrorMsg(errMsg);
          setStatus("error");
        }
      };

      xhr.onerror = () => {
        setErrorMsg("Falha na conexão com o servidor.");
        setStatus("error");
      };

      xhr.responseType = "arraybuffer";
      xhr.send(formData);
    } catch (err) {
      setErrorMsg(String(err));
      setStatus("error");
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 py-10 px-4">
      <div className="max-w-2xl mx-auto space-y-6">

        {/* Header */}
        <div className="text-center space-y-1">
          <h1 className="text-2xl font-bold text-slate-800">
            📄 Consolidador de Reembolso de Despesas
          </h1>
          <p className="text-slate-500 text-sm">
            Projeto Sucuriú — Faça upload dos PDFs e baixe a planilha consolidada
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
              className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${
                dragging
                  ? "border-blue-500 bg-blue-50"
                  : "border-slate-300 bg-white hover:border-blue-400 hover:bg-blue-50"
              }`}
            >
              <input
                ref={inputRef}
                type="file"
                accept=".pdf,application/pdf"
                multiple
                className="hidden"
                onChange={(e) => e.target.files && addFiles(e.target.files)}
              />
              <div className="text-4xl mb-3">📂</div>
              <p className="text-slate-700 font-medium">
                Arraste os PDFs aqui ou clique para selecionar
              </p>
              <p className="text-slate-400 text-sm mt-1">
                Suporta múltiplos arquivos — até 1000 PDFs por vez
              </p>
            </div>

            {/* File list */}
            {files.length > 0 && (
              <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                <div className="px-4 py-3 border-b border-slate-100 flex justify-between items-center">
                  <span className="text-sm font-semibold text-slate-700">
                    {files.length} arquivo{files.length !== 1 ? "s" : ""} selecionado{files.length !== 1 ? "s" : ""}
                  </span>
                  <button
                    onClick={(e) => { e.stopPropagation(); setFiles([]); }}
                    className="text-xs text-slate-400 hover:text-red-500 transition-colors"
                  >
                    Remover todos
                  </button>
                </div>
                <ul className="max-h-48 overflow-y-auto divide-y divide-slate-50">
                  {files.map((f, i) => (
                    <li key={i} className="flex items-center justify-between px-4 py-2 hover:bg-slate-50">
                      <span className="text-sm text-slate-600 truncate max-w-xs">{f.name}</span>
                      <button
                        onClick={() => removeFile(i)}
                        className="text-slate-300 hover:text-red-400 ml-2 flex-shrink-0 transition-colors"
                      >
                        ✕
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Options */}
            <div className="flex items-center gap-2 bg-white rounded-xl border border-slate-200 px-4 py-3">
              <input
                id="includeZeros"
                type="checkbox"
                checked={includeZeros}
                onChange={(e) => setIncludeZeros(e.target.checked)}
                className="w-4 h-4 accent-blue-600"
              />
              <label htmlFor="includeZeros" className="text-sm text-slate-600 cursor-pointer select-none">
                Incluir linhas com Qtd = 0 (itens sem consumo)
              </label>
            </div>

            {/* Error message */}
            {status === "error" && (
              <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
                ❌ {errorMsg}
              </div>
            )}

            {/* Process button */}
            <button
              onClick={processFiles}
              disabled={files.length === 0}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-xl transition-colors text-sm"
            >
              🚀 Processar e Gerar Planilha
            </button>
          </>
        ) : status === "processing" ? (
          /* Processing state */
          <div className="bg-white rounded-xl border border-slate-200 p-8 text-center space-y-4">
            <div className="text-4xl animate-pulse">⚙️</div>
            <p className="text-slate-700 font-medium">
              Processando {files.length} arquivo{files.length !== 1 ? "s" : ""}...
            </p>
            <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
              <div
                className="bg-blue-600 h-2.5 rounded-full transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-slate-400 text-xs">{progress}%</p>
          </div>
        ) : (
          /* Done state */
          <div className="space-y-4">
            <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center space-y-3">
              <div className="text-4xl">✅</div>
              <p className="text-green-800 font-semibold">
                Planilha gerada com sucesso!
              </p>
              <div className="flex justify-center gap-6 text-sm text-green-700">
                <span>📁 {result?.files} arquivo{result?.files !== 1 ? "s" : ""}</span>
                <span>📊 {result?.rows} linhas</span>
              </div>
            </div>

            {downloadUrl && (
              <a
                href={downloadUrl}
                download="reembolso_consolidado.xlsx"
                className="flex items-center justify-center gap-2 w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-3 rounded-xl transition-colors text-sm"
              >
                ⬇️ Baixar reembolso_consolidado.xlsx
              </a>
            )}

            {result?.errors && result.errors.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-amber-100">
                  <p className="text-sm font-semibold text-amber-800">
                    ⚠️ {result.errors.length} aviso{result.errors.length !== 1 ? "s" : ""} durante o processamento
                  </p>
                </div>
                <ul className="max-h-40 overflow-y-auto divide-y divide-amber-50">
                  {result.errors.map((e, i) => (
                    <li key={i} className="px-4 py-2 text-xs text-amber-700">{e}</li>
                  ))}
                </ul>
              </div>
            )}

            <button
              onClick={reset}
              className="w-full bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium py-3 rounded-xl transition-colors text-sm"
            >
              🔄 Processar mais arquivos
            </button>
          </div>
        )}

        <p className="text-center text-xs text-slate-400">
          Projeto Sucuriú · Consolidador de Reembolso de Despesas
        </p>
      </div>
    </div>
  );
}
