// Gráficos SVG próprios: linha, barra e rosca.
//
// Sem lib de gráfico: são três formas, o controle total sobre marcação e cor
// vale mais que a dependência. Toda cor vem de var(--fin-*), então os três
// trocam de tema junto com o resto do app.
//
// Diferente de um viewBox esticado (preserveAspectRatio="none"), aqui o SVG é
// medido e desenhado no tamanho real do container: texto e círculos não
// distorcem em tela larga.

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import "./charts.css";

const GRID = "var(--fin-border)";
const INK = "var(--fin-muted)";

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

/** Largura real do container, acompanhando resize e troca de layout. */
function useLargura(ref, inicial = 560) {
  const [w, setW] = useState(inicial);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const largura = entry.contentRect.width;
      if (largura > 0) setW(largura);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return w;
}

/** Escala com "passos bonitos" (1/2/5 × 10ⁿ) para as linhas de grade. */
function escalaAgradavel(min, max, alvo = 4) {
  if (min === max) {
    if (min === 0) return { min: 0, max: 1, passo: 0.5 };
    const pad = Math.abs(min) * 0.5;
    min -= pad;
    max += pad;
  }
  const bruto = (max - min) / alvo;
  const mag = 10 ** Math.floor(Math.log10(Math.abs(bruto) || 1));
  const norm = bruto / mag;
  const passo = (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag;
  return {
    min: Math.floor(min / passo) * passo,
    max: Math.ceil(max / passo) * passo,
    passo,
  };
}

const ticks = ({ min, max, passo }) => {
  const out = [];
  for (let v = min; v <= max + passo / 2; v += passo) out.push(v);
  return out;
};

/** Tooltip posicionada dentro dos limites do container. */
function Tip({ x, y, largura, label, linhas }) {
  return (
    <div
      className="fin-chart-tip"
      style={{ left: clamp(x, 62, Math.max(largura - 62, 62)), top: y }}
    >
      <span className="fin-chart-tip__lbl">{label}</span>
      {linhas.map((l) => (
        <span key={l.texto} className="fin-chart-tip__row">
          {l.cor && <i style={{ background: l.cor }} />}
          <b>{l.texto}</b>
        </span>
      ))}
    </div>
  );
}

// ── Linha ────────────────────────────────────────────────────────────────────
// Aceita valores negativos: o domínio inclui o zero e a linha do zero fica
// marcada. Num painel de finanças, saldo abaixo de zero precisa ser visível.
export function LineChart({ data, color = "var(--fin-accent)", format = String, height = 168 }) {
  const ref = useRef(null);
  const W = useLargura(ref);
  const [hover, setHover] = useState(null);

  const padT = 12;
  const padB = 22;
  const padL = 8;
  const padR = 8;
  const plotH = height - padT - padB;
  const n = data.length;

  if (!n) return <div ref={ref} style={{ height }} />;

  const vals = data.map((d) => d.valor);
  const esc = escalaAgradavel(Math.min(0, ...vals), Math.max(0, ...vals));
  const step = n > 1 ? (W - padL - padR) / (n - 1) : 0;
  const px = (i) => padL + i * step;
  const py = (v) => padT + plotH - ((v - esc.min) / (esc.max - esc.min)) * plotH;

  const linha = data.map((d, i) => `${i === 0 ? "M" : "L"}${px(i)},${py(d.valor)}`).join(" ");
  const base = py(clamp(0, esc.min, esc.max));
  const area = `${linha} L${px(n - 1)},${base} L${px(0)},${base} Z`;

  const mover = (e) => {
    const rect = ref.current.getBoundingClientRect();
    const i = clamp(Math.round((e.clientX - rect.left - padL) / (step || 1)), 0, n - 1);
    setHover(i);
  };

  return (
    <div
      className="fin-chart"
      ref={ref}
      onMouseMove={mover}
      onMouseLeave={() => setHover(null)}
      style={{ height }}
    >
      <svg width={W} height={height} role="img" aria-label="Gráfico de linha">
        {ticks(esc).map((v) => (
          <line
            key={v}
            x1={padL}
            y1={py(v)}
            x2={W - padR}
            y2={py(v)}
            stroke={GRID}
            strokeWidth="1"
            strokeDasharray={v === 0 ? "none" : "3,4"}
            opacity={v === 0 ? 1 : 0.7}
          />
        ))}

        <path d={area} fill={color} opacity="0.11" />
        <path
          d={linha}
          fill="none"
          stroke={color}
          strokeWidth="1.75"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {hover !== null && (
          <line
            className="fin-chart-cross"
            x1={px(hover)}
            y1={padT}
            x2={px(hover)}
            y2={padT + plotH}
            stroke={color}
            strokeWidth="1"
            strokeDasharray="3,3"
            opacity="0.55"
          />
        )}

        {data.map((d, i) => (
          <circle
            key={d.label + i}
            cx={px(i)}
            cy={py(d.valor)}
            r={hover === i ? 4.5 : 2.5}
            fill={color}
            stroke="var(--fin-surface)"
            strokeWidth={hover === i ? 2 : 0}
          />
        ))}

        {data.map((d, i) =>
          // Em tela estreita, um rótulo a cada dois, senão vira borrão.
          i % (W < 380 ? 3 : W < 560 ? 2 : 1) === 0 || i === n - 1 ? (
            <text
              key={`l${i}`}
              x={px(i)}
              y={height - 6}
              textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"}
              fontSize="10"
              fill={INK}
            >
              {d.label}
            </text>
          ) : null,
        )}
      </svg>

      {hover !== null && (
        <Tip
          x={px(hover)}
          y={py(data[hover].valor)}
          largura={W}
          label={data[hover].label}
          linhas={[{ texto: format(data[hover].valor), cor: color }]}
        />
      )}
    </div>
  );
}

// ── Barras (uma ou mais séries agrupadas) ────────────────────────────────────
export function BarChart({
  data,
  series = [{ nome: "", cor: "var(--fin-accent)" }],
  format = String,
  height = 168,
}) {
  const ref = useRef(null);
  const W = useLargura(ref);
  const [hover, setHover] = useState(null);

  const padT = 12;
  const padB = 22;
  const padL = 6;
  const padR = 6;
  const plotH = height - padT - padB;
  const n = data.length;

  if (!n) return <div ref={ref} style={{ height }} />;

  // Normaliza: cada ponto vira sempre um array de valores.
  const pontos = data.map((d) => ({
    label: d.label,
    valores: d.valores ?? [d.valor ?? 0],
  }));

  const esc = escalaAgradavel(0, Math.max(...pontos.flatMap((p) => p.valores), 0));
  const py = (v) => padT + plotH - (v / (esc.max || 1)) * plotH;

  const slot = (W - padL - padR) / n;
  const grupoW = Math.min(slot * 0.68, 20 * series.length + 4);
  const barW = Math.max((grupoW - 2 * (series.length - 1)) / series.length, 3);

  return (
    <div
      className="fin-chart"
      ref={ref}
      onMouseLeave={() => setHover(null)}
      style={{ height }}
    >
      <svg
        width={W}
        height={height}
        role="img"
        aria-label="Gráfico de barras"
        className={hover !== null ? "has-hover" : ""}
      >
        {ticks(esc).map((v) => (
          <line
            key={v}
            x1={padL}
            y1={py(v)}
            x2={W - padR}
            y2={py(v)}
            stroke={GRID}
            strokeWidth="1"
            strokeDasharray={v === 0 ? "none" : "3,4"}
            opacity="0.7"
          />
        ))}

        {pontos.map((p, i) => {
          const x0 = padL + i * slot + (slot - grupoW) / 2;
          return (
            <g key={p.label + i} className={`fin-bar-g${hover === i ? " is-hover" : ""}`}>
              {p.valores.map((v, s) => {
                const h = Math.max(((v / (esc.max || 1)) * plotH) | 0, v > 0 ? 2 : 0);
                return (
                  <rect
                    key={s}
                    x={x0 + s * (barW + 2)}
                    y={padT + plotH - h}
                    width={barW}
                    height={h}
                    rx="2"
                    fill={series[s]?.cor || "var(--fin-accent)"}
                  />
                );
              })}
              {/* Alvo de hover do grupo inteiro: barra zerada também responde. */}
              <rect
                x={padL + i * slot}
                y={padT}
                width={slot}
                height={plotH}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
              />
              <text
                x={padL + i * slot + slot / 2}
                y={height - 6}
                textAnchor="middle"
                fontSize="10"
                fill={INK}
              >
                {slot > 22 ? p.label : ""}
              </text>
            </g>
          );
        })}
      </svg>

      {hover !== null && (
        <Tip
          x={padL + hover * slot + slot / 2}
          y={py(Math.max(...pontos[hover].valores))}
          largura={W}
          label={pontos[hover].label}
          linhas={pontos[hover].valores.map((v, s) => ({
            texto: `${series[s]?.nome ? `${series[s].nome}: ` : ""}${format(v)}`,
            cor: series[s]?.cor,
          }))}
        />
      )}
    </div>
  );
}

// ── Rosca ────────────────────────────────────────────────────────────────────
// A legenda é um filtro acumulativo: clicar isola as fatias escolhidas e o
// centro recalcula o total só com elas.
export function DonutChart({ segments, format = String, unidade = "total", size = 152 }) {
  const [sel, setSel] = useState(() => new Set());
  const [hover, setHover] = useState(null);

  // Se uma categoria some dos dados (troca de mês), o filtro dela vira lixo.
  useEffect(() => {
    setSel((prev) => {
      const validos = new Set(segments.map((s) => s.label));
      const next = new Set([...prev].filter((l) => validos.has(l)));
      return next.size === prev.size ? prev : next;
    });
  }, [segments]);

  const visiveis = sel.size ? segments.filter((s) => sel.has(s.label)) : segments;
  const total = visiveis.reduce((s, x) => s + x.valor, 0);

  const r = size / 2 - 14;
  const c = size / 2;
  const circ = 2 * Math.PI * r;
  const gap = segments.length > 1 ? 3 : 0;
  let acc = 0;

  const foco = hover ? segments.find((s) => s.label === hover) : null;

  return (
    <div className="fin-donut">
      <svg
        width={size}
        height={size}
        role="img"
        aria-label="Distribuição por categoria"
        onMouseLeave={() => setHover(null)}
        style={{ flexShrink: 0 }}
      >
        <circle cx={c} cy={c} r={r} fill="none" stroke={GRID} strokeWidth="13" />

        {total > 0 &&
          visiveis
            .filter((s) => s.valor > 0)
            .map((s) => {
              const frac = s.valor / total;
              const len = Math.max(frac * circ - gap, 0.5);
              const el = (
                <circle
                  key={s.label}
                  className="fin-donut__seg"
                  cx={c}
                  cy={c}
                  r={r}
                  fill="none"
                  stroke={s.cor}
                  strokeWidth={hover === s.label ? 16 : 13}
                  strokeDasharray={`${len} ${circ - len}`}
                  strokeDashoffset={-acc}
                  transform={`rotate(-90 ${c} ${c})`}
                  opacity={hover && hover !== s.label ? 0.35 : 1}
                  onMouseEnter={() => setHover(s.label)}
                />
              );
              acc += frac * circ;
              return el;
            })}

        <text
          x={c}
          y={c - 1}
          textAnchor="middle"
          fontSize="14"
          fontWeight="700"
          fill="var(--fin-text)"
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          {format(foco ? foco.valor : total)}
        </text>
        <text x={c} y={c + 15} textAnchor="middle" fontSize="10" fill={INK}>
          {foco ? foco.label : unidade}
        </text>
      </svg>

      <div className="fin-donut__leg">
        {segments.map((s) => {
          const estado = sel.size === 0 ? "" : sel.has(s.label) ? " on" : " off";
          const pct = total > 0 && (sel.size === 0 || sel.has(s.label))
            ? Math.round((s.valor / total) * 100)
            : null;
          return (
            <button
              key={s.label}
              type="button"
              className={`fin-donut__leg-item${estado}`}
              onClick={() =>
                setSel((prev) => {
                  const next = new Set(prev);
                  next.has(s.label) ? next.delete(s.label) : next.add(s.label);
                  return next;
                })
              }
              onMouseEnter={() => setHover(s.label)}
              onMouseLeave={() => setHover(null)}
            >
              <i style={{ background: s.cor }} />
              <span className="fin-donut__leg-name">{s.label}</span>
              <span className="fin-donut__leg-val">
                {pct !== null ? `${pct}%` : "·"}
              </span>
            </button>
          );
        })}
        {sel.size > 0 && (
          <button type="button" className="fin-donut__clear" onClick={() => setSel(new Set())}>
            Limpar filtro ({sel.size})
          </button>
        )}
      </div>
    </div>
  );
}

// ── Vazio ────────────────────────────────────────────────────────────────────
// Nunca deixar o buraco do gráfico na tela: desenha a grade fantasma para o
// card manter a altura e diz por que não há dado.
export function EmptyChart({ label, height = 168 }) {
  return (
    <div className="fin-chart-empty" style={{ height }}>
      <svg width="100%" height="100%" viewBox="0 0 400 120" preserveAspectRatio="none" aria-hidden="true">
        {[24, 60, 96].map((y) => (
          <line
            key={y}
            x1="0"
            y1={y}
            x2="400"
            y2={y}
            stroke={GRID}
            strokeWidth="1"
            strokeDasharray="3,4"
          />
        ))}
        {[24, 76, 128, 180, 232, 284, 336].map((x, i) => (
          <rect
            key={x}
            x={x}
            y={96 - (i % 3) * 14 - 10}
            width={26}
            height={(i % 3) * 14 + 10}
            rx="2"
            fill={GRID}
          />
        ))}
      </svg>
      <span className="fin-chart-empty__label">{label}</span>
    </div>
  );
}
