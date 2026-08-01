// 등록 사용자 목록 + 신규 등록 모달(얼굴 촬영)

import { CircleUser, Plus, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { User } from "../types";

function RegisterModal({
  onClose,
  onRegistered,
}: {
  onClose: () => void;
  onRegistered: () => void;
}) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // 모달 열리면 카메라를 등록 모드로 전환
  useEffect(() => {
    api.setCameraMode("register").catch(() => {});
    return () => {
      api.setCameraMode("idle").catch(() => {});
    };
  }, []);

  const submit = async () => {
    if (!name.trim() || !phone.trim()) {
      setError("이름과 연락처를 입력해 주세요.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.registerUser(name.trim(), phone.trim(), deviceId.trim() || null);
      onRegistered();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "등록에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal fade-in-up">
        <div style={{ display: "flex", alignItems: "flex-start" }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 18, fontWeight: 700 }}>사용자 신규 등록</span>
            <span style={{ fontSize: 12, color: "var(--text-2)" }}>
              이름과 연락처 입력 후 얼굴을 등록해 주세요.
            </span>
          </div>
          <button onClick={onClose} style={{ color: "var(--text-3)" }}>
            <X size={18} />
          </button>
        </div>

        <div className="field-group">
          <span className="field-label">이름</span>
          <div className="field-box">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="예: 홍길동"
              autoFocus
            />
          </div>
        </div>

        <div className="field-group">
          <span className="field-label">연락처</span>
          <div className="field-box mono">
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="예: 010-1234-5678"
            />
          </div>
        </div>

        <div className="field-group">
          <div className="field-label-row">
            <span className="field-label">구명조끼 장치 ID</span>
            <span className="field-hint">선택 · 예: jacket-1</span>
          </div>
          <div className="field-box mono">
            <input
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
              placeholder="장치 미배정 시 비워 두세요"
            />
          </div>
        </div>

        {/* 등록용 카메라 미리보기 */}
        <div
          style={{
            position: "relative",
            width: "100%",
            height: 210,
            background: "var(--cam-bg)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 10,
            flexShrink: 0,
          }}
        >
          <img
            src="/api/video_feed"
            alt="등록 카메라"
            style={{
              position: "absolute",
              inset: 0,
              width: "100%",
              height: "100%",
              objectFit: "cover",
            }}
          />
          <div
            style={{
              position: "relative",
              width: 110,
              height: 134,
              border: "2px solid var(--accent)",
              borderRadius: "50%",
              opacity: 0.85,
              pointerEvents: "none",
            }}
          />
          <span
            style={{
              position: "relative",
              fontSize: 11,
              color: "var(--text-2)",
              textShadow: "0 1px 4px #000",
            }}
          >
            얼굴 영역만 인식합니다
          </span>
        </div>

        {error && (
          <div
            className="chip danger"
            style={{ width: "100%", whiteSpace: "normal" }}
          >
            {error}
          </div>
        )}

        <div style={{ display: "flex", gap: 10 }}>
          <button
            className="btn btn-primary"
            style={{ flex: 1 }}
            onClick={submit}
            disabled={busy}
          >
            {busy ? "등록 중…" : "얼굴 촬영 & 등록"}
          </button>
          <button className="btn btn-secondary" onClick={onClose}>
            취소
          </button>
        </div>
      </div>
    </div>
  );
}

export function UsersScreen() {
  const [users, setUsers] = useState<User[]>([]);
  const [showRegister, setShowRegister] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<User | null>(null);

  const reload = useCallback(() => {
    api.users().then(setUsers).catch(() => {});
  }, []);

  useEffect(reload, [reload]);

  const doDelete = async (user: User) => {
    try {
      await api.deleteUser(user.id);
    } finally {
      setConfirmDelete(null);
      reload();
    }
  };

  return (
    <div className="content">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="page-title">등록 사용자 목록</h1>
          <p className="page-desc">얼굴 인식을 위해 시스템에 등록된 선원 대장입니다.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowRegister(true)}>
          ＋ 신규 사용자 등록
        </button>
      </div>

      <section
        className="panel"
        style={{
          flex: 1,
          minHeight: 0,
          width: "100%",
          display: "flex",
          flexDirection: "column",
          gap: 14,
          padding: 18,
        }}
      >
        <h2 className="panel-title">시스템 등록 사용 대장</h2>

        <div
          style={{
            flex: 1,
            minHeight: 0,
            overflowY: "auto",
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 14,
            alignContent: "start",
          }}
        >
          {users.map((user) => (
            <div
              key={user.id}
              className="cell"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 14,
                padding: 16,
                borderRadius: 10,
              }}
            >
              <div
                style={{
                  width: 52,
                  height: 52,
                  borderRadius: 26,
                  background: "var(--panel-2)",
                  border: "1px solid var(--border)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  overflow: "hidden",
                  color: "var(--text-3)",
                  flexShrink: 0,
                }}
              >
                {user.photo ? (
                  <img
                    src={`/faces/${user.photo.split("/").pop()}`}
                    alt={user.name}
                    style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  />
                ) : (
                  <CircleUser size={26} />
                )}
              </div>
              <div
                style={{
                  flex: 1,
                  minWidth: 0,
                  display: "flex",
                  flexDirection: "column",
                  gap: 3,
                }}
              >
                <span
                  style={{ fontSize: 15, fontWeight: 700, color: "var(--accent)" }}
                >
                  {user.name}
                </span>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                    color: "var(--text-2)",
                  }}
                >
                  {user.phone}
                </span>
                <span style={{ fontSize: 10, color: "var(--text-3)" }}>
                  등록일 {user.registered_at.split(" ")[0]}
                  {user.device_id ? ` · ${user.device_id}` : ""}
                </span>
              </div>
              <button
                className="btn btn-danger btn-sm"
                style={{ padding: "6px 12px", fontSize: 11 }}
                onClick={() => setConfirmDelete(user)}
              >
                삭제
              </button>
            </div>
          ))}

          {/* 신규 등록 타일 */}
          <button
            onClick={() => setShowRegister(true)}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              padding: "22px 16px",
              background: "#ffffff03",
              border: "1px dashed var(--border)",
              borderRadius: 10,
              color: "var(--text-3)",
              minHeight: 86,
            }}
          >
            <Plus size={20} />
            <span style={{ fontSize: 12 }}>신규 사용자 등록</span>
          </button>
        </div>
      </section>

      {showRegister && (
        <RegisterModal onClose={() => setShowRegister(false)} onRegistered={reload} />
      )}

      {confirmDelete && (
        <div className="modal-backdrop">
          <div className="modal fade-in-up" style={{ width: 380 }}>
            <span style={{ fontSize: 16, fontWeight: 700 }}>사용자 삭제</span>
            <span style={{ fontSize: 13, color: "var(--text-2)" }}>
              '{confirmDelete.name}' 님의 정보와 얼굴 사진을 삭제할까요? 삭제 후에는
              얼굴 인식으로 승선할 수 없습니다.
            </span>
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button
                className="btn btn-secondary"
                onClick={() => setConfirmDelete(null)}
              >
                취소
              </button>
              <button className="btn btn-danger" onClick={() => doDelete(confirmDelete)}>
                삭제
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
