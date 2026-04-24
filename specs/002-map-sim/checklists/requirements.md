# Specification Quality Checklist: Map Simulator (Map Sim)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-04-25
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
  - *Note*：spec 中提及 `asyncio.Lock`、`aiohttp`、Haversine 公式等，是因為 Map Sim 是**感測器模擬器基礎設施**，其介面契約（Port、HTTP 方法、`asyncio.Lock` 並發保證）本身就是下游感測器依賴的「可見行為」。與 `specs/001-uds/spec.md` 一致，此類低階契約屬於 PoC 規格本體而非實作細節。
- [x] Focused on user value and business needs（User Stories 1/2/3 各自指向一個明確業務消費者）
- [x] Written for non-technical stakeholders（背景、使用者情境皆以繁體中文業務語言描述）
- [x] All mandatory sections completed（User Scenarios、Requirements、Success Criteria、Assumptions 齊備）

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous（FR-MS-001~015 皆可由契約測試或整合測試驗證）
- [x] Success criteria are measurable（SC-MS-001~009 皆含具體數值或時間上下界）
- [x] Success criteria are technology-agnostic（SC 僅描述延遲、正確性、容量、可用性等使用者可觀察指標）
- [x] All acceptance scenarios are defined（三個 User Story 共 14 個 Given-When-Then 情境）
- [x] Edge cases are identified（Edge Cases 段落涵蓋缺欄位、未知 drone_id、radius_m=0/負、並發、LANDED 過渡、非法 timestamp、空登錄表、額外欄位、include_lost 行為、極大 radius 共 10 個案例）
- [x] Scope is clearly bounded（Out of Scope 明列 8 項排除）
- [x] Dependencies and assumptions identified（Assumptions 段落與 §6 依賴章節）

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria（FR 編號與 User Story Acceptance Scenarios 可對應）
- [x] User scenarios cover primary flows（P1 接收 / P1 查詢 / P1 TTL）
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification（同 Content Quality 首項說明）

## Notes

- 所有必填契約欄位嚴格對齊 `dev-docs/001-uds.md` §七 與 `specs/001-uds/contracts/rest-api.md` §3.2（UDS 已實作的 8 欄位），`model / operator_lat / operator_lon` 僅 Sentrycs 內部使用，不列為 Map Sim 必填。
- 所有 User Story 均 P1：Map Sim 的三個主要能力（接收 / 查詢 / TTL）彼此依賴、缺一不可，無 P2/P3 可降級。
- 未觸發 `[NEEDS CLARIFICATION]`：規格來源（`03-map-simulator-spec.md`、`08-api-icd.md`、`dev-docs/001-uds.md`）對介面、TTL、CLI 預設值已完整描述，本 spec 僅做跨文件整合與使用者情境化。
