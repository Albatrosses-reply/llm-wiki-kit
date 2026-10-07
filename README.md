# 📚 LLM Wiki 키트

매일 아침 **관심 저널의 새 논문을 메일로** 받고, 읽고 싶은 논문을 버튼 하나로 고르면 **AI(ChatGPT Codex 또는 Claude)가 Obsidian 위키 페이지로 정리**해 주는 도구입니다.

```
매일 아침 (내 컴퓨터에서 자동)
  ① 부동산·경제·재무·경영 저널 신간 수집 → 초록 보충 → 한글 요약
  ② Gmail로 아침 메일 (논문마다 📥 위키 후보로 버튼)
  ③ 버튼으로 고른 논문 → 다음 아침 AI가 위키 페이지 작성
       wiki/sources/논문.md  (연구 질문·방법·결과·한계, 내 평가 초안)
       wiki/concepts/개념.md (개념 연결)
  ④ PDF를 다운로드 폴더에 받아 두면 본문 기준으로 다시 작성
Obsidian으로 열어 보고, AI에게 "질문: …"이라고 물으면 위키를 근거로 답합니다.
```

## 필요한 것
- Mac 또는 Windows 컴퓨터 (자동 작업이 이 컴퓨터에서 돕니다. 꺼져 있으면 켜진 뒤 실행)
- **ChatGPT**(Codex) 또는 **Claude**(Claude Code) 계정
- **Gmail 계정** + 앱 비밀번호 (설치 중에 만듭니다)
- [Obsidian](https://obsidian.md) (무료)
- 선택: Elsevier·Semantic Scholar API 키(초록 보충), Zotero

---

## 설치 방법 1: AI에게 맡기기 (권장)

1. **AI 도구 설치·로그인** (하나만)
   - ChatGPT: [Codex CLI](https://developers.openai.com/codex/cli) 설치 → 터미널에서 `codex` → ChatGPT로 로그인
   - Claude: [Claude Code](https://code.claude.com) 설치 → 터미널에서 `claude` → 로그인
2. 터미널에서 AI를 열고 아래를 **그대로 붙여 넣기**:

```
https://raw.githubusercontent.com/Albatrosses-reply/llm-wiki-kit/main/AGENTS.md 를 읽고,
그 안내대로 내 컴퓨터에 LLM Wiki를 설치해 줘.
나는 프로그래밍을 잘 모르니까 단계마다 쉽게 설명하고, 정할 것은 하나씩 물어봐 줘.
```

AI가 저장소 내려받기, 설정 질문(보관소 위치, Gmail 주소, 받을 저널, 관심 키워드), 설치, 시험 메일까지 진행합니다.
**Gmail 앱 비밀번호와 API 키는 AI에게 알려 주지 마세요.** AI가 안내하는 대로 **새 터미널 창**에서 직접 `python3 wiki.py secrets`를 실행해 입력합니다(화면에 보이지 않습니다).

---

## 설치 방법 2: 직접 하기

```bash
git clone https://github.com/Albatrosses-reply/llm-wiki-kit.git ~/llm-wiki-kit
cd ~/llm-wiki-kit
python3 install.py          # 질문에 답하기 (Windows는 python)
python3 wiki.py secrets     # Gmail 앱 비밀번호, API 키 입력
python3 wiki.py test-mail   # 시험 메일
python3 wiki.py daily --days 7   # 첫 아침 메일 (몇 분 걸림)
```
마지막으로 Obsidian → **폴더를 보관소로 열기** → 설치 때 정한 보관소 폴더(기본 `~/LLM-Wiki`).

### Gmail 앱 비밀번호 만들기
1. [Google 계정 → 보안](https://myaccount.google.com/security)에서 **2단계 인증** 켜기
2. [앱 비밀번호](https://myaccount.google.com/apppasswords)에서 이름(예: `LLM Wiki`) 입력 → **만들기** → 16자리 비밀번호 복사
3. `python3 wiki.py secrets`에 붙여 넣기

학교 Google 계정은 앱 비밀번호가 막혀 있을 수 있습니다. 그러면 개인 Gmail을 쓰세요.

### API 키 (선택, 초록이 빈 논문을 줄임)
- **Elsevier** (JUE·RSUE·JHE·Land Use Policy·Cities 등): [dev.elsevier.com](https://dev.elsevier.com) → I want an API key. **본인이 직접** 받으세요(공유 금지).
- **Semantic Scholar** (Taylor & Francis 저널 등): [semanticscholar.org/product/api](https://www.semanticscholar.org/product/api)

---

## 매일 쓰는 법
1. 아침 메일에서 읽을 논문의 **📥 위키 후보로**를 눌러 열린 메일을 그대로 보냅니다. 여러 편은 **📥 목록 메일 작성**에서 `[x]`.
   (Obsidian `inbox/alerts/날짜.md`에서 체크박스를 `[x]`로 바꿔도 됩니다.)
2. 다음 아침 `wiki/sources/`에 페이지가 생깁니다. 메일 맨 위에 결과 한 줄이 나옵니다.
3. 중요한 논문은 **✍️ Contribution · ⚠️ Caveats · 🧭 내 연구와의 관계**를 직접 고쳐 쓰고 `<!-- llm-draft … -->` 줄을 지우세요. 그 섹션은 이후 AI가 건드리지 않습니다.
4. PDF는 학교 도서관에서 받아 **다운로드 폴더에 두기만** 하면 다음 아침 본문 기준으로 다시 씁니다.
5. 보관소 폴더에서 Codex·Claude를 열고 `질문: 주택 공급 규제가 임대료에 미치는 영향은?` → 위키 근거 답변. `저장해줘`라고 하면 정리 페이지로 남습니다.

## 명령 모음
| 명령 | 하는 일 |
|---|---|
| `python3 wiki.py doctor` | 설치 상태 점검 (`--engine`이면 AI 실행까지) |
| `python3 wiki.py daily` | 매일 작업을 지금 실행 |
| `python3 wiki.py ingest` | 고른 논문 위키 페이지를 지금 작성 (`--key 인용키`로 한 편) |
| `python3 wiki.py poll` | 메일 회신·Obsidian 체크 지금 확인 |
| `python3 wiki.py test-mail` | 시험 메일 |
| `python3 wiki.py secrets` | 비밀번호·키 입력 |
| `python3 install.py --reconfigure` | 설정 다시 (저널·키워드·시간·AI 바꾸기) |
| `python3 wiki.py schedule --remove` | 자동 실행 끄기 |

설정 파일 `~/.llm-wiki/settings.toml`, 비밀값 `~/.llm-wiki/.env`(본인만 읽기), 기록 `~/.llm-wiki/logs/wiki.log`.

## 알아 둘 점
- AI 사용량: 하루 위키 페이지 최대 5편 + 한글 요약 몇 번. ChatGPT·Claude 구독의 사용 한도 안에서 돕니다(`settings.toml`의 `max_ingest`로 조절).
- 유료 논문 PDF를 자동으로 받지 않고, 출판사 웹페이지를 긁지 않습니다. 공식 API(Crossref, OpenAlex, Elsevier, Semantic Scholar)만 씁니다.
- PDF와 위키는 내 컴퓨터에만 있습니다. 보관소를 공개 저장소에 올리지 마세요(PDF 저작권).
- Windows용 예약 실행은 PowerShell 작업 스케줄러로 등록합니다. 문제가 있으면 `python wiki.py doctor` 결과와 함께 알려 주세요.

## 라이선스
MIT. 논문 서지·초록의 권리는 각 출판사에 있습니다.
