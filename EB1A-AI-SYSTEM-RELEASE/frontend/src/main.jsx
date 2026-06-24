import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Archive, CheckCircle2, FileText, LoaderCircle, Play, Scale, UploadCloud, X } from "lucide-react";
import "./index.css";

const stages = ["upload", "ocr", "classify", "petition", "exhibits", "complete"];

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || "Request failed");
  return body;
}

function App() {
  const [files, setFiles] = useState([]);
  const [caseName, setCaseName] = useState("");
  const [caseData, setCaseData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const picker = useRef(null);

  const activeStage = useMemo(() => Math.max(0, stages.indexOf(caseData?.stage || "upload")), [caseData]);
  useEffect(() => {
    if (!caseData?.id || !["processing", "uploaded"].includes(caseData.status)) return;
    const timer = setInterval(async () => {
      try {
        const payload = await api(`/case/${caseData.id}`);
        setCaseData(payload.case);
      } catch (reason) { setError(reason.message); }
    }, 1500);
    return () => clearInterval(timer);
  }, [caseData?.id, caseData?.status]);

  async function upload() {
    if (!files.length) return setError("Choose at least one case file.");
    setBusy(true); setError("");
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    form.append("case_name", caseName);
    try { setCaseData((await api("/upload_case", { method: "POST", body: form })).case); }
    catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  }

  async function run() {
    setBusy(true); setError("");
    try { setCaseData((await api(`/run_pipeline/${caseData.id}`, { method: "POST" })).case); }
    catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  }

  return (
    <main className="relative min-h-screen px-5 py-8 sm:px-8 lg:px-12">
      <div className="mx-auto max-w-6xl">
        <header className="mb-10 flex items-start justify-between gap-6 border-b border-ink/15 pb-7">
          <div><div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-[.28em] text-moss"><Scale size={16}/> Internal legal workflow</div>
          <h1 className="max-w-3xl text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">One case. One pipeline.<br/><span className="text-moss">A reviewable EB-1A package.</span></h1></div>
          <span className="hidden rounded-full border border-moss/25 bg-white/60 px-4 py-2 text-xs font-semibold text-moss sm:block">CONSOLIDATED RELEASE</span>
        </header>

        {error && <div role="alert" className="mb-6 flex items-center justify-between rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800">{error}<button onClick={() => setError("")} aria-label="Dismiss"><X size={17}/></button></div>}

        <div className="grid gap-6 lg:grid-cols-[1.05fr_.95fr]">
          <section className="rounded-2xl border border-ink/10 bg-white/75 p-6 shadow-card backdrop-blur sm:p-8">
            <div className="mb-6 flex items-center gap-3"><div className="grid h-10 w-10 place-items-center rounded-xl bg-moss text-white"><UploadCloud size={20}/></div><div><h2 className="text-lg font-semibold">Upload case materials</h2><p className="text-sm text-ink/55">ZIP, PDF, DOCX, images, or TXT</p></div></div>
            <label className="mb-5 block"><span className="mb-2 block text-xs font-bold uppercase tracking-wider text-ink/60">Case name</span><input value={caseName} onChange={(e) => setCaseName(e.target.value)} placeholder="e.g. Chen — EB-1A review" className="focus-ring w-full rounded-xl border border-ink/15 bg-paper/50 px-4 py-3"/></label>
            <button onClick={() => picker.current?.click()} className="focus-ring flex min-h-44 w-full flex-col items-center justify-center rounded-2xl border border-dashed border-moss/40 bg-moss/[.04] p-6 text-center transition hover:bg-moss/[.08]"><UploadCloud className="mb-3 text-moss" size={30}/><strong>Choose case files</strong><span className="mt-1 text-sm text-ink/50">Multiple files are accepted</span></button>
            <input ref={picker} type="file" multiple className="hidden" accept=".zip,.pdf,.docx,.png,.jpg,.jpeg,.tif,.tiff,.webp,.txt" onChange={(e) => setFiles([...e.target.files])}/>
            {!!files.length && <ul className="mt-4 space-y-2">{files.map((file) => <li key={`${file.name}-${file.size}`} className="flex items-center justify-between rounded-lg bg-paper px-3 py-2 text-sm"><span className="truncate"><FileText className="mr-2 inline text-moss" size={15}/>{file.name}</span><span className="ml-3 text-xs text-ink/45">{(file.size/1024/1024).toFixed(1)} MB</span></li>)}</ul>}
            <button disabled={busy || !files.length} onClick={upload} className="focus-ring mt-5 w-full rounded-xl bg-ink px-5 py-3.5 font-semibold text-white transition hover:bg-moss disabled:cursor-not-allowed disabled:opacity-40">{busy ? "Uploading…" : "Create case"}</button>
          </section>

          <section className="rounded-2xl bg-ink p-6 text-white shadow-card sm:p-8">
            <div className="mb-7 flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-[.2em] text-gold">Pipeline status</p><h2 className="mt-1 text-2xl font-semibold">{caseData?.name || "No active case"}</h2></div>{caseData?.status?.startsWith("completed") && <CheckCircle2 className="text-emerald-300" size={28}/>}</div>
            <div className="mb-7"><div className="mb-2 flex justify-between text-sm"><span className="capitalize text-white/65">{caseData?.status?.replaceAll("_", " ") || "Waiting for upload"}</span><strong>{caseData?.progress || 0}%</strong></div><div className="h-2 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-gold transition-all duration-500" style={{ width: `${caseData?.progress || 0}%` }}/></div></div>
            <ol className="space-y-3">{stages.map((stage, index) => { const done = caseData && index < activeStage; const current = caseData && index === activeStage; return <li key={stage} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 ${current ? "bg-white/10" : ""}`}><span className={`grid h-7 w-7 place-items-center rounded-full text-xs font-bold ${done ? "bg-emerald-300 text-ink" : current ? "bg-gold text-ink" : "bg-white/10 text-white/45"}`}>{current && caseData.status === "processing" ? <LoaderCircle className="animate-spin" size={14}/> : index + 1}</span><span className={done || current ? "text-white" : "text-white/40"}>{stage === "classify" ? "Evidence classification" : stage === "complete" ? "ZIP export" : stage[0].toUpperCase() + stage.slice(1)}</span></li>; })}</ol>
            <div className="mt-8 grid gap-3 sm:grid-cols-2"><button disabled={!caseData || busy || caseData.status === "processing"} onClick={run} className="focus-ring flex items-center justify-center gap-2 rounded-xl bg-gold px-4 py-3 font-bold text-ink disabled:opacity-35"><Play size={17}/> Run pipeline</button><a aria-disabled={!caseData?.download_url} href={caseData?.download_url || undefined} className={`focus-ring flex items-center justify-center gap-2 rounded-xl border border-white/20 px-4 py-3 font-bold ${caseData?.download_url ? "hover:bg-white/10" : "pointer-events-none opacity-35"}`}><Archive size={17}/> Export ZIP</a></div>
            <p className="mt-6 text-xs leading-relaxed text-white/45">Internal preparation only. Generated documents require qualified attorney review and are not filed with USCIS by this system.</p>
          </section>
        </div>

        {caseData?.logs?.length > 0 && <section className="mt-6 rounded-2xl border border-ink/10 bg-white/65 p-6"><h3 className="mb-4 font-semibold">Processing log</h3><div className="max-h-56 space-y-2 overflow-auto font-mono text-xs">{caseData.logs.slice().reverse().map((log, index) => <div key={`${log.timestamp}-${index}`} className="grid grid-cols-[90px_75px_1fr] gap-3 border-b border-ink/5 pb-2"><span className="text-ink/45">{new Date(log.timestamp).toLocaleTimeString()}</span><span className={log.status === "error" ? "text-red-700" : "text-moss"}>{log.stage}</span><span>{log.message}</span></div>)}</div></section>}
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<React.StrictMode><App/></React.StrictMode>);
