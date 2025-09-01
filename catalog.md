# カタログ仕様と運用ガイド

本ドキュメントは、当カタログのデータ仕様・公開方法・参照方法の決定版です。今後の更新は本ガイドに準拠してください。

## 公開と配布

- ベースURL: `https://shun2741.github.io/yutai-catalog`
- 必須ファイル: `catalog-manifest.json`（ベース直下）、本体JSON（例: `catalog-YYYY-MM-DD.json`）
- `manifest.url`: 本体JSONへの相対パス（現行はベース直下のファイル名）
- `manifest.hash`: 本体JSONのSHA-256（内容変更で必ず変化）
- 文字コード: UTF-8、改行: LF

例（実体）

```json
// https://shun2741.github.io/yutai-catalog/catalog-manifest.json
{
  "version": "2025-08-31",
  "hash": "...",
  "url": "catalog-2025-08-31.json"
}
```

## データスキーマ（CSV → JSON）

Pydanticモデルは `src/pipeline/models.py` に定義。CSVカラムは以下に準拠。

### companies.csv

- id: 安定ID（内部参照用、変更禁止）
- name: 会社名（例: コロワイド）
- ticker: 証券コード等の一意キー（未上場は空OK）
- chainIds: 編集時は空でよい（ビルド時に chains.csv から自動付与）
- voucherTypes: 優待カテゴリ配列（カンマ区切り）
- notes: 任意メモ

ポイント:

- 所属チェーンの一次情報（SoT）は `chains.csv` の `companyIds` 側です。
- `companies.csv` の `chainIds` はビルド時に自動で上書きされるため、人手で編集しません。

### chains.csv

- id: 安定ID（例: `chain-kappasushi`）
- displayName: 表示名（例: かっぱ寿司 / ステーキ宮）
- category: 大分類（例: 飲食）
- companyIds: 親会社ID配列（カンマ区切り）
- voucherTypes: 優待カテゴリ配列（カンマ区切り）
- tags: 補助タグ（カンマ区切り、例: 寿司/ステーキ）
- url: 公式URL

例:

```csv
id,displayName,category,companyIds,voucherTypes,tags,url
chain-kappasushi,かっぱ寿司,飲食,comp-colowide,食事,寿司,https://www.kappasushi.jp/
chain-miya,ステーキ宮,飲食,comp-colowide,食事,ステーキ,https://www.miya.com/
```

### stores.csv

- id: 安定ID（例: `store-miya-osm-node-4516947894`）
- chainId: 所属チェーンID
- name: 店名（支店名は後置: 例「ステーキ宮 仙台中田店」）
- address: 住所（空可）
- lat, lng: 数値（WGS84、小数5–6桁推奨）
- tags: カンマ区切り（例: ステーキ）
- updatedAt: ISO8601 UTC（例: 2025-08-31T10:06:38.822Z）

OSM取り込み時のID命名規則:

- ノード: `store-<chain>-osm-node-<osm_id>`
- ウェイ: `store-<chain>-osm-way-<osm_id>`
- リレーション: `store-<chain>-osm-relation-<osm_id>`

フィルタ例（ステーキ宮）: 「駐車場」「宮川」等の誤検出は除外。

## 値の標準化

- voucherTypes（許容値）: `食事` / `買い物` / `レジャー` / `その他`
- 代表カテゴリは配列の先頭に置く（UIの既定値に利用）

## ID設計と安定性

- `companies[].id`, `chains[].id`, `stores[].id` は一度発行したら変更しない
- 名称変更は `name` / `displayName` のみ更新

## リレーション運用の要点

- チェーン→会社: `chains.csv` の `companyIds` を唯一の真実（SoT）として編集
- 会社→チェーン: `companies[].chainIds` はビルド時に自動付与（人手で編集しない）
- 例（コロワイド）: `chains.csv` 側で `companyIds=comp-colowide` を持つチェーン（例: かっぱ寿司/ステーキ宮）を管理

## 位置情報の品質

- 緯度経度はWGS84で正確に（0/0等の欠損禁止）
- 桁数は5–6桁（約1–10m）を推奨
- 住所は簡潔に（都道府県/市区町村/丁目・番地 程度）

## ビルドとリリース

- 生成: `PYTHONPATH=./src python -m pipeline.build`
- 出力: `dist/catalog-YYYY-MM-DD.json`, `dist/catalog-manifest.json`
- 配布: GitHub Actionsで `dist/` を Pages にデプロイ（サイトルートに配置される）
- バージョン: `YYYY-MM-DD` は論理バージョン。`manifest.version` と整合。

## 管理UI（ローカル簡易ツール）

- 目的: `companies.csv` と `chains.csv` を手で地道に追加するための簡易UI。
- 起動:
  - 依存を導入: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
  - サーバ起動: `PYTHONPATH=./src python src/admin_app.py`
  - ブラウザ: `http://127.0.0.1:5000/`
- 機能:
  - Companies: 一覧表示、追加（chainIds は空でOK。ビルド時に自動付与）
  - Chains: 一覧表示、追加（companyIds はカンマ区切り）
  - Stores: OSMインポート（試験的）で名称パターンから店舗を追加（重複除外）
- 注意:
  - ローカル編集後はビルド→コミット/プッシュで本番へ反映
  - OSMインポートは名称ベースのため誤検出に注意。必要に応じてCSVを微修正

## クライアントからの参照（PWA）

- マニフェスト取得: `https://shun2741.github.io/yutai-catalog/catalog-manifest.json`
- 本体取得: 上記 `manifest.url` を連結（例: `.../catalog-2025-08-31.json`）
- キャッシュ対策: `?v=manifest.hash` などクエリ付与を推奨
- CSP: `connect-src 'self' https://shun2741.github.io;` を許可
- SW: キャッシュキーに `manifest.hash` を含め、更新検知を確実化

コード例（ブラウザ/Fetch）:

```js
const base = 'https://shun2741.github.io/yutai-catalog';
const mani = await fetch(`${base}/catalog-manifest.json?ts=${Date.now()}`).then(r=>r.json());
const catalog = await fetch(`${base}/${mani.url}?v=${mani.hash || mani.version}`).then(r=>r.json());
```

ローカル開発時に外部URLを参照する例（Vite）:

```env
# .env.development
VITE_CATALOG_BASE=https://shun2741.github.io/yutai-catalog
```

```js
const base = import.meta.env.VITE_CATALOG_BASE || '/catalog';
const mani = await fetch(`${base}/catalog-manifest.json?ts=${Date.now()}`).then(r=>r.json());
const catalog = await fetch(`${base}/${mani.url}?v=${mani.hash || mani.version}`).then(r=>r.json());
```

## データ更新手順（標準）

1) `data/*.csv` を編集（本ガイドの型・命名・値規則に準拠）
2) ローカルビルドし、JSONに `chain/company/store` が正しく出力されることを確認
3) コミット＆ push（Actions が実行され Pages が更新）
4) 公開URLで `catalog-manifest.json` の `hash/url/version` 更新を確認
5) 本体JSONに追加・更新分（例: ステーキ宮）が含まれるか spot-check

## テスト/検証

- 生成後のJSON構造は `src/pipeline/models.py` に準拠していること（型崩れ禁止）
- 公開後はベースURL直下のマニフェスト/本体を直接確認
- 不要な差分抑制のため、CSVの値は意図なく並び替えない

## 注意事項

- 既存IDの削除や再利用は禁止。閉店等は `stores` から削除するが、ID再利用はしない
- `ticker` 変更は所有データ突合に影響。必要時は移行手順を明記する
- 本体JSONは可能なら5MB未満を目安（将来的に分割配信を検討）

以上に準拠して更新してください。クライアントは外部最新カタログを自動参照し、一覧・地図・フォームへ反映されます。
