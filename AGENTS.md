# AGENTS.md — LLM Wiki 설치를 돕는 AI용 안내 (Codex, Claude Code)

이 저장소는 **LLM Wiki 키트**다. 설치하면 사용자 컴퓨터에서 매일 자동으로:
저널 신간 수집 → 초록 보충·한글 요약 → Gmail 아침 메일(📥 위키 후보로 버튼) → 고른 논문을 AI(Codex 또는 Claude)가 Obsidian 위키 페이지로 작성.

사용자는 대부분 **프로그래밍 경험이 없는 학생**이다. 아래 순서대로 한 단계씩 진행하고, 단계마다 무엇을 했는지 한국어로 짧게 알려 준다. 정할 것은 **한 번에 하나씩** 묻는다.

## 절대 규칙
1. **Gmail 앱 비밀번호·API 키를 묻거나, 읽거나, 출력하거나, 파일·명령 인자에 넣지 않는다.** 사용자가 직접 별도 터미널 창에서 `python wiki.py secrets`로 입력한다. 사용자가 채팅에 붙여 넣으면 쓰지 말고, 노출됐으니 새로 발급받으라고 안내한다(Gmail 앱 비밀번호는 삭제 후 재발급).
2. `~/.llm-wiki/.env` 파일을 열거나 내용을 출력하지 않는다. 확인은 `python wiki.py doctor`로만 한다(있음/없음만 보인다).
3. 사용자의 기존 Obsidian 보관소나 폴더를 지우거나 덮어쓰지 않는다. 보관소는 새 폴더를 기본으로 한다.
4. 출판사 웹페이지를 긁거나 유료 PDF를 자동으로 내려받는 기능을 추가하지 않는다.

## 설치 순서

### 0. 준비 확인 (하나씩 실행해 결과를 보고 판단)
| 확인 | 명령 | 없으면 |
|---|---|---|
| Python 3.11 이상 | `python3 --version` (Windows: `python --version`) | macOS `brew install python@3.12` 또는 python.org / Windows `winget install Python.Python.3.12` 후 새 터미널 |
| git | `git --version` | 없으면 GitHub에서 ZIP으로 받아 풀어도 된다 |
| AI 도구 로그인 | Codex: `codex login status` / Claude: `claude --version` | 지금 이 대화를 하고 있는 도구가 곧 위키를 쓸 도구다. 다른 도구를 원하면 그 도구 설치·로그인 |
| Codex 최신 | `codex --version` | 오래되면 `npm install -g @openai/codex@latest` (또는 `brew upgrade codex`). 오래된 Codex는 "requires a newer version" 오류로 실패한다 |

### 1. 키트 내려받기
```bash
git clone https://github.com/Albatrosses-reply/llm-wiki-kit.git ~/llm-wiki-kit
cd ~/llm-wiki-kit
```
Windows PowerShell은 `~` 대신 `$HOME`을 쓴다. 이후 명령은 모두 이 폴더에서 실행한다. Windows에서는 `python3` 대신 `python`.

### 2. 설정 묻기 (한 번에 하나씩)
| 키 | 질문 | 기본값 / 참고 |
|---|---|---|
| `vault` | Obsidian 보관소를 어디에 만들까요? | `~/LLM-Wiki`. macOS는 문서·데스크탑·iCloud·Google Drive 폴더를 피한다(예약 실행이 접근을 못 할 수 있음) |
| `engine` | 위키를 쓸 AI: `codex`(ChatGPT) / `claude` | 지금 쓰는 도구 |
| `gmail` | 앱 비밀번호를 만들 Gmail 주소 | 필수. 학교 Google 계정은 앱 비밀번호가 막혀 있을 수 있으니 개인 Gmail 권장 |
| `recipient` | 메일 받을 주소 | 비우면 gmail과 같음 |
| `daily_time` | 매일 몇 시에 받을까요? | `05:30` (그 시각에 컴퓨터가 꺼져 있으면 켜진 뒤 실행) |
| `realestate` | 부동산 저널: `핵심+확장` / `핵심만` / `안 받음` | `핵심+확장`. 목록은 `wikikit/journals.toml` |
| `economics`, `finance`, `management` | 경제학·재무·경영 주요 저널도 받을까요? | `false` |
| `keyword_filter` | 그 분야는 키워드에 맞는 논문만 받을까요? | `true` |
| `keywords` | 관심 키워드(영어, 쉼표) | `housing, rent*, mortgage*, house price*, real estate, zoning`. 한국어로 말하면 영어로 바꿔 제안 |
| `extra_journals` | 더 받을 저널(영문 이름이나 ISSN) | 빈 문자열 |
| `interests` | 내 관심 주제 한두 문장(한국어) | 위키가 '내 연구와의 관계' 초안에 쓴다 |
| `zotero` | Zotero를 쓰면 고른 논문을 Zotero에도 넣을까요? | `true` (Zotero가 켜져 있을 때만 동작) |

답을 `answers.json`으로 저장한다(비밀값 키는 넣지 않는다. 넣으면 설치기가 거부한다):
```json
{"vault": "~/LLM-Wiki", "engine": "codex", "gmail": "student@gmail.com", "recipient": "", "daily_time": "05:30",
 "realestate": "핵심+확장", "economics": false, "finance": false, "management": false, "keyword_filter": true,
 "keywords": "housing, rent*, mortgage*", "extra_journals": "", "interests": "주택 임대료와 공급 규제", "zotero": true}
```

### 3. 설치 실행
```bash
python3 install.py --answers answers.json
```
가상환경(.venv)·패키지·설정(`~/.llm-wiki/settings.toml`)·보관소·예약 실행(macOS launchd, Windows 작업 스케줄러)을 만든다. 출력의 "추가 저널" 줄을 사용자에게 보여 주고 이름이 맞는지 확인받는다. 끝나면 `answers.json`을 지운다.

### 4. Gmail 앱 비밀번호 (사용자가 직접)
사용자에게 안내만 한다:
1. https://myaccount.google.com/security 에서 **2단계 인증**을 켠다(이미 켜져 있으면 넘어감).
2. https://myaccount.google.com/apppasswords 에서 앱 이름(예: `LLM Wiki`)을 넣고 **만들기** → 16자리 비밀번호가 나온다.
3. **새 터미널 창**을 열고(이 대화 창이 아니라) 아래를 실행해 붙여 넣는다. 입력은 화면에 보이지 않는다.
   ```bash
   cd ~/llm-wiki-kit
   python3 wiki.py secrets
   ```
   Elsevier·Semantic Scholar 키는 있으면 같이 넣고, 없으면 Enter로 넘어간다.
4. 끝났다고 하면 `python3 wiki.py doctor`로 "Gmail 앱 비밀번호 있음"을 확인한다.

### 5. 시험
```bash
python3 wiki.py test-mail          # 시험 메일 도착 확인을 사용자에게 묻는다
python3 wiki.py doctor --engine    # AI 실행 시험까지
python3 wiki.py daily --days 7     # 첫 아침 메일 (몇 분 걸림)
```
첫 메일이 오면 사용자에게 아무 논문이나 **📥 위키 후보로**를 눌러 보내 보라고 한 뒤, `python3 wiki.py ingest`로 위키 페이지가 바로 만들어지는지 보여 준다(1~3분).

### 6. Obsidian
Obsidian 설치(https://obsidian.md) → **폴더를 보관소로 열기** → 3단계의 보관소 폴더. `index.md`와 `wiki/sources/`의 새 페이지를 보여 준다.

### 마지막 안내 (사용자에게)
- 매일 정한 시각에 메일이 온다. 읽을 논문은 **📥 위키 후보로**(또는 Obsidian `inbox/alerts`에서 `[x]`). 다음 아침에 위키 페이지가 생긴다.
- PDF는 다운로드 폴더에 받아 두기만 하면 다음 아침 자동으로 연결되어 본문 기준으로 다시 쓴다.
- 보관소 폴더에서 AI를 열고 "질문: …"이라고 물으면 위키를 근거로 답한다(보관소의 AGENTS.md 규약).
- 설정 바꾸기: `python3 install.py --reconfigure` / 지금 실행: `python3 wiki.py daily` / 점검: `python3 wiki.py doctor`

## 문제 해결
| 증상 | 확인·조치 |
|---|---|
| `Gmail 로그인 실패` | 일반 비밀번호를 넣었거나 2단계 인증이 꺼짐. 앱 비밀번호를 새로 만들어 `wiki.py secrets` 다시 |
| 학교 계정에 앱 비밀번호 메뉴가 없음 | 학교 관리자가 막은 것. 개인 Gmail로 `install.py --reconfigure` |
| `codex ... requires a newer version` | Codex 업데이트 (0단계) |
| 위키 작성 실패 반복 | `~/.llm-wiki/logs/wiki.log` 끝부분 확인. AI 로그인 만료면 다시 로그인. `python3 wiki.py ingest`로 바로 재시도 |
| 예약 실행이 안 됨 (macOS) | `python3 wiki.py doctor`의 예약 실행 줄 확인 → `python3 wiki.py schedule`. 보관소가 문서·iCloud·Drive 폴더면 홈 바로 아래로 옮기고 `install.py --reconfigure` |
| 예약 실행이 안 됨 (Windows) | 작업 스케줄러에서 `LLMWiki-daily`, `LLMWiki-poll` 확인 → `python wiki.py schedule` |
| 다운로드 폴더 PDF가 연결 안 됨 | PDF 첫 두 쪽에 DOI가 없으면 못 맞춘다. `raw/pdf/인용키.pdf`로 직접 넣는다 |
| 메일 회신이 후보로 안 잡힘 | 제목에 `WIKI-STAR`가 있어야 한다(버튼이 자동으로 넣는다). 30분마다 확인. 바로 하려면 `python3 wiki.py poll` |

## 코드 구조 (수정 요청을 받았을 때)
```
install.py            설치기(질문 또는 --answers) → .venv, settings.toml, 보관소, 예약 실행
wiki.py               실행 진입점(.venv로 다시 실행): daily, poll, ingest, test-mail, secrets, schedule, doctor, index
wikikit/cli.py        명령 구현. daily = poll → Zotero → ingest → 수집 → 초록 보충 → 요약 → 메일 → Obsidian 목록
wikikit/collect.py    Crossref ∪ OpenAlex 수집, 비논문 제외, 키워드 점수
wikikit/abstracts.py  초록 보충(Elsevier API, Semantic Scholar)
wikikit/summarize.py  한글 요약(여러 편을 묶어 AI 한 번 호출)
wikikit/mailer.py     아침 메일(HTML, 📥 버튼 = mailto WIKI-STAR <hash>)
wikikit/curate.py     메일 회신(IMAP)·Obsidian 체크 → 후보 노트
wikikit/ingest.py     AI로 wiki/sources/<인용키>.md 작성, 서지 강제·사람 섹션 보존·규약 파일 복구
wikikit/pdfs.py       다운로드 폴더 PDF를 DOI로 맞춰 raw/pdf, raw/text
wikikit/llm.py        codex exec / claude -p 실행(프롬프트는 표준입력)
wikikit/scheduler.py  launchd / 작업 스케줄러 등록
wikikit/journals.toml 저널 묶음
vault_template/       새 보관소 템플릿(AGENTS.md 위키 규약, 페이지 템플릿, Obsidian 보기)
```
- 고친 뒤 `.venv/bin/python -m unittest discover -s tests` (Windows `.venv\Scripts\python`).
- 실제 메일·AI를 쓰지 않는 시험: `LLM_WIKI_HOME=/tmp/x python3 install.py --answers ...` 로 따로 설치해 `wiki.py daily --no-mail`.
- 사용자에게 보이는 문구·로그는 한국어.
