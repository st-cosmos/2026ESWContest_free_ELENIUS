// 운항 기록지: 출입항 단위 아코디언 · 펼치면 승선 로그 + 항해 1분 간격 운항 상세
// (시뮬레이터 배속으로 운항하면 실제 기록 간격은 배속만큼 좁아진다)

import { Archive, ChevronDown, ChevronRight, Route, Users } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { AppState, VoyageDetail, VoyageSummary } from "../types";

function hhmm(ts: string | null): string | null {
  return ts ? (ts.split(" ")[1]?.slice(0, 5) ?? null) : null;
}

function rangeLabel(v: VoyageSummary): string {
  const dep = hhmm(v.departed_at) ?? "-";
  const arr = hhmm(v.arrived_at);
  return arr ? `${dep} 출항 → ${arr} 입항` : `${dep} 출항 → 입항 대기`;
}

function PanelHead({
  icon: Icon,
  title,
  meta,
}: {
  icon: typeof Users;
  title: string;
  meta: string;
}) {
  return (
    <div className="rec-panel-head">
      <Icon size={14} color="var(--accent)" />
      <span className="rec-panel-title">{title}</span>
      <span className="rec-panel-meta">{meta}</span>
    </div>
  );
}

function ExpandedBody({ detail }: { detail: VoyageDetail | null }) {
  if (!detail) {
    return (
      <div className="rec-body rec-body-loading">기록을 불러오는 중…</div>
    );
  }

  return (
    <div className="rec-body">
      {/* 승선 로그 */}
      <section className="rec-panel">
        <PanelHead
          icon={Users}
          title="승선 로그"
          meta={`얼굴 인식 승선 ${detail.crew.length}명`}
        />
        <div className="rec-table">
          <div className="rec-thead">
            <span style={{ width: 36 }}>No.</span>
            <span style={{ flex: 1 }}>이름</span>
            <span style={{ flex: 1 }}>전화번호</span>
            <span style={{ width: 74, textAlign: "right" }}>승선 시간</span>
          </div>
          {detail.crew.length === 0 && (
            <p className="rec-empty">승선 기록이 없습니다</p>
          )}
          {detail.crew.map((c, i) => (
            <div className="rec-row" key={`${c.user_id}-${i}`}>
              <span className="t-mono t-dim" style={{ width: 36 }}>
                {String(i + 1).padStart(2, "0")}
              </span>
              <span style={{ flex: 1, fontWeight: 700 }}>{c.name}</span>
              <span className="t-mono t-soft" style={{ flex: 1 }}>
                {c.phone}
              </span>
              <span
                className="t-mono t-accent"
                style={{ width: 74, textAlign: "right", fontWeight: 600 }}
              >
                {c.time}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* 운항 상세 */}
      <section className="rec-panel">
        <PanelHead
          icon={Route}
          title="운항 상세"
          meta={`항해 1분 간격 · 총 ${detail.points.length}건`}
        />
        <div className="rec-table">
          <div className="rec-thead">
            <span style={{ width: 150 }}>시간</span>
            <span style={{ flex: 1 }}>좌표</span>
          </div>
          {detail.points.map((p, i) => (
            <div className="rec-row" key={`${p.ts}-${i}`}>
              <span className="t-mono t-soft" style={{ width: 150 }}>
                {p.ts}
              </span>
              <span className="t-mono" style={{ flex: 1 }}>
                {p.coord}
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export function VoyageRecord({ state }: { state: AppState }) {
  const [voyages, setVoyages] = useState<VoyageSummary[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<VoyageDetail | null>(null);
  const firstLoad = useRef(true);

  const loadList = useCallback(async () => {
    try {
      const list = await api.voyages();
      setVoyages(list);
      if (firstLoad.current && list.length > 0) {
        firstLoad.current = false;
        setOpenId(list[0].id);
      }
    } catch {
      /* 폴링이 다음 주기에 재시도 */
    }
  }, []);

  // 출입항이 발생하면 목록을 갱신한다
  useEffect(() => {
    loadList();
  }, [loadList, state.voyage.active, state.voyage.current_id]);

  // 펼친 기록의 상세를 불러온다 (운항 중이면 주기적으로 최신화)
  useEffect(() => {
    if (!openId) {
      setDetail(null);
      return;
    }
    let alive = true;
    const fetchDetail = () => {
      api
        .voyage(openId)
        .then((d) => alive && setDetail(d))
        .catch(() => alive && setDetail(null));
    };
    setDetail(null);
    fetchDetail();

    const isActive = voyages.find((v) => v.id === openId)?.status === "active";
    if (!isActive) return () => { alive = false; };
    const t = setInterval(fetchDetail, 15000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [openId, voyages]);

  return (
    <div className="content">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="page-title">운항 기록지</h1>
          <p className="page-desc">
            출항부터 입항까지를 하나의 기록으로 관리합니다. 기록을 펼치면 승선 로그와
            항해 1분 간격 운항 상세를 함께 확인할 수 있습니다.
          </p>
        </div>
        <div className="chip neutral">
          <Archive size={14} />
          <span>로그 보관 기간 1년</span>
        </div>
      </div>

      <div className="rec-list">
        {voyages.length === 0 && (
          <div className="rec-placeholder">
            운항 기록이 없습니다 · 출항을 확정하면 기록이 시작됩니다
          </div>
        )}

        {voyages.map((v) => {
          const open = v.id === openId;
          const active = v.status === "active";
          return (
            <article
              key={v.id}
              className={`rec-item${open ? " open" : ""}`}
            >
              <button
                className="rec-head"
                onClick={() => setOpenId(open ? null : v.id)}
                aria-expanded={open}
              >
                {open ? (
                  <ChevronDown size={16} color="var(--accent)" />
                ) : (
                  <ChevronRight size={16} color="var(--text-3)" />
                )}
                <span className={`rec-date${open ? " on" : ""}`}>{v.date}</span>
                <span className="rec-range">{rangeLabel(v)}</span>
                <span style={{ flex: 1 }} />
                <span className="rec-crew">
                  <Users size={12} />
                  승선 {v.crew_count}명
                </span>
                <span className={`badge ${active ? "warn" : "accent"}`}>
                  <span className={`dot${active ? " pulse" : ""}`} />
                  {active ? "운항 중" : "운항 완료"}
                </span>
              </button>

              {open && <ExpandedBody detail={detail} />}
            </article>
          );
        })}
      </div>
    </div>
  );
}
