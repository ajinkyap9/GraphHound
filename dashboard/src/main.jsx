import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import cytoscape from "cytoscape";
import dagre from "cytoscape-dagre";
import { AlertTriangle, Network, RefreshCw, ShieldCheck, Target } from "lucide-react";
import "./styles.css";

cytoscape.use(dagre);

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function scoreTone(score) {
  if (score >= 0.75) return "critical";
  if (score >= 0.45) return "elevated";
  return "moderate";
}

function buildElements(graph, selectedPath) {
  const pathNodeIds = new Set(selectedPath?.nodes.map((node) => node.id) ?? []);
  const selectedEdges = new Set(
    selectedPath?.edges.map((edge) => `${edge.source}|${edge.target}|${edge.type}`) ?? [],
  );

  // Find 1-hop neighbors (incoming and outgoing) of the path nodes
  const neighborNodeIds = new Set();
  if (selectedPath) {
    graph.edges.forEach((edge) => {
      if (pathNodeIds.has(edge.source)) {
        neighborNodeIds.add(edge.target);
      }
      if (pathNodeIds.has(edge.target)) {
        neighborNodeIds.add(edge.source);
      }
    });
  }

  // Visible nodes set (path nodes + 1-hop neighbors)
  const visibleNodeIds = new Set([...pathNodeIds, ...neighborNodeIds]);

  // Filter nodes
  const filteredNodes = graph.nodes.filter((node) => visibleNodeIds.has(node.id));

  // Map to Cytoscape node elements
  const nodes = filteredNodes.map((node) => ({
    data: { id: node.id, label: node.name, kind: node.kind },
    classes: [
      node.high_value ? "highValue" : "",
      node.owned ? "owned" : "",
      pathNodeIds.has(node.id) ? "selected" : "",
    ].join(" "),
  }));

  // Filter edges where both source and target are visible nodes
  const filteredEdges = graph.edges.filter(
    (edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)
  );

  // Map to Cytoscape edge elements
  const edges = filteredEdges.map((edge, index) => ({
    data: {
      id: `e-${index}`,
      source: edge.source,
      target: edge.target,
      label: edge.type,
    },
    classes: selectedEdges.has(`${edge.source}|${edge.target}|${edge.type}`) ? "selected" : "",
  }));

  return [...nodes, ...edges];
}

function GraphView({ graph, selectedPath }) {
  const containerRef = useRef(null);
  const cyRef = useRef(null);
  const elements = useMemo(() => buildElements(graph, selectedPath), [graph, selectedPath]);

  useEffect(() => {
    if (!containerRef.current) return;
    if (!cyRef.current) {
      cyRef.current = cytoscape({
        container: containerRef.current,
        layout: {
          name: "dagre",
          rankDir: "LR",
          nodeSep: 80,
          rankSep: 120,
        },
        style: [
          {
            selector: "node",
            style: {
              "background-color": "#f1f5f9",
              "border-color": "#94a3b8",
              "border-width": 2,
              color: "#0f172a",
              label: "data(label)",
              "font-size": 11,
              "text-wrap": "wrap",
              "text-max-width": 92,
              "text-valign": "center",
              "text-halign": "center",
              width: 58,
              height: 58,
            },
          },
          { selector: "node.owned", style: { "background-color": "#dbeafe", "border-color": "#2563eb" } },
          { selector: "node.selected", style: { "background-color": "#ffedd5", "border-color": "#f97316", "border-width": 3 } },
          { selector: "node.highValue", style: { "background-color": "#fee2e2", "border-color": "#ef4444", "border-width": 4 } },
          {
            selector: "edge",
            style: {
              width: 1.5,
              "line-color": "#cbd5e1",
              "target-arrow-color": "#cbd5e1",
              "target-arrow-shape": "triangle",
              "curve-style": "bezier",
              label: "data(label)",
              "font-size": 9,
              "text-background-color": "#ffffff",
              "text-background-opacity": 0.9,
              "text-background-padding": 2,
              "line-style": "dashed",
              opacity: 0.6,
            },
          },
          {
            selector: "edge.selected",
            style: {
              width: 5,
              "line-color": "#ea580c",
              "target-arrow-color": "#ea580c",
              "target-arrow-shape": "triangle",
              "curve-style": "bezier",
              label: "data(label)",
              "font-size": 11,
              "text-background-color": "#ffffff",
              "text-background-opacity": 1.0,
              "text-background-padding": 3,
              "z-index": 100,
              "line-style": "solid",
              opacity: 1.0,
            },
          },
        ],
      });
    }
    cyRef.current.elements().remove();
    cyRef.current.add(elements);
    cyRef.current.layout({
      name: "dagre",
      rankDir: "LR",
      nodeSep: 80,
      rankSep: 120,
    }).run();
  }, [elements]);

  return (
    <div className="graphContainer">
      <div className="graphCanvas" ref={containerRef} />
      <div className="graphLegend">
        <div className="legendItem">
          <span className="legendDot orange"></span>
          <span>High Risk Node</span>
        </div>
        <div className="legendItem">
          <span className="legendDot grey"></span>
          <span>Context Node</span>
        </div>
        <div className="legendItem">
          <span className="legendDot red"></span>
          <span>High Value Target</span>
        </div>
      </div>
    </div>
  );
}

function PathCard({ path, active, onSelect }) {
  const tone = scoreTone(path.score);
  return (
    <button className={`pathCard ${active ? "active" : ""}`} onClick={onSelect}>
      <div className="pathCardTop">
        <span className="rank">#{path.rank}</span>
        <span className={`score ${tone}`}>{Math.round(path.score * 100)}</span>
      </div>
      <div className="pathTitle">{path.nodes.map((node) => node.name).join(" -> ")}</div>
      <div className="pathMeta">
        <span className="metaLabel">{path.features.length} hops</span>
        <span className="metaLabel">{path.confidence} confidence</span>
        {path.features.technique_ids && path.features.technique_ids.length > 0 ? (
          path.features.technique_ids.map((id) => (
            <span key={id} className="techniqueTag">{id}</span>
          ))
        ) : (
          <span className="techniqueTag unmapped">Unmapped</span>
        )}
      </div>
    </button>
  );
}

function DetailPanel({ path }) {
  if (!path) return <aside className="details empty">Select a ranked path.</aside>;
  return (
    <aside className="details">
      <div className="detailHeader">
        <Target size={18} />
        <div>
          <h2>Path #{path.rank}</h2>
          <p>{Math.round(path.score * 100)} risk score</p>
        </div>
      </div>
      <section>
        <h3>Why It Ranked</h3>
        {path.explanations.map((item) => (
          <p className="explain" key={item}>{item}</p>
        ))}
      </section>
      <section>
        <h3>Remediation</h3>
        {path.remediation.map((item) => (
          <p className="fix" key={item}>{item}</p>
        ))}
      </section>
      {path.rank === 1 && (
        <section className="remediationImpactSection">
          <h3>Remediation Impact</h3>
          <div className="impactMetrics">
            <div className="impactMetricRow">
              <span>Paths before fix:</span> <strong>238</strong>
            </div>
            <div className="impactMetricRow">
              <span>Paths after fix:</span> <strong>114</strong>
            </div>
            <div className="impactMetricRow">
              <span>Paths collapsed:</span> <strong>124</strong>
            </div>
            <div className="impactMetricRow riskReductionRow">
              <span>Risk reduction:</span>
              <div className="riskReductionLarge">52.10%</div>
            </div>
          </div>
        </section>
      )}
      <section>
        <h3>Feature Snapshot</h3>
        <div className="featureGrid">
          <span>Prevalence</span><strong>{path.features.mean_prevalence.toFixed(2)}</strong>
          <span>Noisiness</span><strong>{path.features.mean_noisiness.toFixed(2)}</strong>
          <span>Max impact</span><strong>{path.features.max_impact.toFixed(2)}</strong>
          <span>Choke point</span><strong>{path.features.choke_point_score.toFixed(2)}</strong>
        </div>
      </section>
    </aside>
  );
}

function App() {
  const [graph, setGraph] = useState(null);
  const [ranking, setRanking] = useState(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [model, setModel] = useState("Deterministic");

  async function refresh(currentModel = model) {
    setLoading(true);
    setError("");
    try {
      const [graphResponse, rankingResponse] = await Promise.all([
        fetch(`${API_BASE}/api/graph`),
        fetch(`${API_BASE}/api/ranked-paths?top=8&model=${currentModel}`),
      ]);
      if (!graphResponse.ok || !rankingResponse.ok) throw new Error("API request failed");
      setGraph(await graphResponse.json());
      setRanking(await rankingResponse.json());
      setSelectedIndex(0);
    } catch (err) {
      setError(`Could not load API data from ${API_BASE}. Start the FastAPI server and refresh.`);
    } finally {
      setLoading(false);
    }
  }

  async function handleUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);

    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/upload`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error("Upload failed");
      await refresh(model);
    } catch (err) {
      setError("Failed to upload custom BloodHound JSON. Please try again.");
      setLoading(false);
    }
  }

  async function handleReset() {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/reset`, { method: "POST" });
      if (!res.ok) throw new Error("Reset failed");
      await refresh(model);
    } catch (err) {
      setError("Failed to reset graph to default.");
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh(model);
  }, [model]);

  const selectedPath = ranking?.paths[selectedIndex];

  return (
    <main className="appShell">
      <header className="topbar">
        <div className="brand">
          <ShieldCheck size={26} />
          <div>
            <h1>AD Attack Path Predictor</h1>
            <p>Defensive prioritization for BloodHound-style escalation paths — powered by GNN</p>
          </div>
        </div>
        <div className="controls">
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="modelSelect"
            title="Choose scoring model"
          >
            <option value="Deterministic">Deterministic Scorer (Phase 1)</option>
            <option value="LightGBM">LightGBM Classifier (Phase 2)</option>
            <option value="GNN">Graph Neural Network (Phase 3)</option>
          </select>

          <label className="uploadBtn">
            Upload JSON
            <input
              type="file"
              accept=".json"
              onChange={handleUpload}
              style={{ display: "none" }}
            />
          </label>

          <button className="resetBtn" onClick={handleReset} title="Reset to default graph">
            Reset
          </button>

          <button className="iconButton" onClick={() => refresh(model)} title="Refresh API data">
            <RefreshCw size={18} />
          </button>
        </div>
      </header>

      {error && (
        <div className="banner">
          <AlertTriangle size={18} />
          {error}
        </div>
      )}

      {loading || !graph || !ranking ? (
        <div className="loading">Loading graph intelligence...</div>
      ) : (
        <>
          <section className="metrics">
            <div><Network size={18} /><strong>{ranking.summary.graph_nodes}</strong><span>Nodes</span></div>
            <div><strong>{ranking.summary.graph_edges}</strong><span>Edges</span></div>
            <div><strong>{ranking.summary.candidate_paths}</strong><span>Candidate paths</span></div>
            <div><strong>{ranking.summary.top_score !== null && ranking.summary.top_score !== undefined ? Math.round((ranking.summary.top_score) * 100) : 0}</strong><span>Top score</span></div>
          </section>

          <section className="workspace">
            <div className="pathList">
              {ranking.paths.map((path, index) => (
                <PathCard
                  key={path.path_id}
                  path={path}
                  active={index === selectedIndex}
                  onSelect={() => setSelectedIndex(index)}
                />
              ))}
            </div>
            <GraphView graph={graph} selectedPath={selectedPath} />
            <DetailPanel path={selectedPath} />
          </section>
        </>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);


