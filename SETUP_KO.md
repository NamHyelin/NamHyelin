# 외부 API 없이 Scholar → JSON → README

Hyelin Nam의 Scholar ID `KTjNYtAAAAAJ`가 설정되어 있습니다.
Python 표준 라이브러리로 Google Scholar HTML을 직접 읽습니다. API 키, 유료 서비스, Vercel, 추가 Python 패키지가 필요하지 않습니다.

## 동작

1. 하루 한 번 Scholar 프로필의 인용 순 첫 페이지(최대 100개)를 요청합니다.
2. 제목·저자·출판 정보·연도·인용 수를 추출해 `data/scholar.json`에 저장합니다.
3. 인용 수 내림차순 상위 4개를 README 표로 작성합니다. 동률은 제목 순입니다.
4. JSON과 README를 GitHub에 커밋합니다.

README를 볼 때마다 실시간 조회하는 방식이 아니라 저장된 최신 성공 결과를 표시합니다.
별도 사이트를 두어도 Google의 서버 요청 차단이 해결되는 것은 아니므로 GitHub 저장소를 저장소로 사용합니다.

## 중요한 현재 상태

개발 환경에서 실제 프로필에 직접 요청한 결과 HTTP 429(요청 제한)가 반환되었습니다.
따라서 코드와 테스트는 준비되었지만 실제 논문 데이터는 아직 수집되지 않았습니다.
GitHub Actions에서도 403/429나 CAPTCHA가 발생할 수 있습니다. 이때 자동 갱신을 보장할 수 없습니다.
프로그램은 차단을 우회하거나 반복 요청하지 않고 중단하며, 기존 JSON과 표를 유지합니다.
첫 실행부터 차단되면 실제 표는 생성되지 않습니다. 아래 로컬 실행 또는 저장 HTML 가져오기를 사용할 수 있습니다.

## 1. GitHub에 넣기

ZIP을 풀고 자신의 **프로필 저장소**(일반적으로 `사용자명/사용자명`) 기본 브랜치에 다음 세 파일을 추가합니다.

| 경로 | 역할 |
| --- | --- |
| `scripts/update_scholar.py` | 직접 조회·추출·저장·표 생성 |
| `scholar-config.json` | Scholar ID와 표시 논문 수 |
| `.github/workflows/update-scholar.yml` | 예약/수동 실행 |

GitHub 웹에서 Add file → Create new file을 누르고 위 경로를 이름으로 입력한 다음 해당 파일의 내용을 붙여 넣어 Commit changes 하세요.
압축 파일 자체를 올리는 것이 아닙니다. `.github`는 숨김 폴더이므로 Mac에서는 Command+Shift+. 로 표시할 수 있습니다.
기존 README는 교체하지 마세요. `README-SNIPPET.md`의 내용을 기존 README의 원하는 위치에 **한 번만** 붙여 넣습니다.
기존 Vercel 배지 HTML은 직접 삭제하세요. 마커 없이 실행하면 새 표가 README 끝에 추가됩니다.

## 2. 실행

GitHub → Actions → Update Scholar publications → Run workflow → Run workflow.
성공하면 README 표와 `data/scholar.json`이 자동으로 커밋됩니다.
실패하면 Actions의 해당 실행 로그에서 HTTP 상태나 오류를 확인하세요.
키 발급이나 Secret 등록은 필요하지 않습니다.

예약은 매일 13:23 UTC(보스턴 겨울 08:23/여름 09:23, 한국 22:23)입니다.
GitHub 예약 실행은 지연될 수 있습니다. 즉시 조회를 시도하려면 Run workflow를 누르면 됩니다.
공개 저장소가 장기간 비활성 상태라면 GitHub가 예약 실행을 중단할 수 있으므로 Actions 상태를 확인하세요.

## 3. GitHub에서 차단되면 내 컴퓨터에서 실행

Python 3.10 이상이 있는 컴퓨터에서 프로필 저장소를 내려받고 저장소 폴더에서 실행하세요.

```bash
python3 scripts/update_scholar.py
```

성공하면 변경된 `README.md`, `data/scholar.json`을 GitHub에 업로드하거나 커밋/푸시합니다.
로컬 네트워크에서도 Google이 요청을 거부할 수 있습니다. 브라우저에서 열리는 것과 Python 요청 성공 여부는 다릅니다.
로컬 자동화를 원하면 같은 명령을 본인 컴퓨터의 작업 스케줄러에 등록할 수 있지만, 이 패키지는 컴퓨터의 스케줄러를 설정하지 않습니다.

## 4. 브라우저는 열리는데 Python 요청만 차단될 때

논문 정보를 손으로 입력할 필요는 없습니다. 본인 브라우저에서 정상적으로 열리는 페이지를 HTML로 저장해서 동일한 추출기에 전달할 수 있습니다.

1. https://scholar.google.com/citations?user=KTjNYtAAAAAJ&hl=en&pagesize=100 를 엽니다.
2. 인용 수가 높은 순인지 확인하고 필요한 논문이 로드되어 있는지 확인합니다.
3. 브라우저의 페이지 저장 기능으로 HTML 파일을 저장합니다. PDF나 스크린샷이 아닌 HTML이어야 합니다.
4. 저장한 파일을 지정해 실행합니다.

```bash
python3 scripts/update_scholar.py --html "$HOME/Downloads/scholar.html"
```

이 방식은 **수동 스냅샷 가져오기**이며 자동 fetch는 아닙니다. 저장된 행 중에서 정렬하므로 표시하고 싶은 논문이 페이지에 로드되어 있어야 합니다.
JSON에는 `acquisition: saved_html`로 기록되고 표의 날짜는 가져온 시각이며, 원본 페이지의 갱신 시각은 아닙니다.
HTML 원본에는 불필요한 브라우저 페이지 정보가 있을 수 있으므로 GitHub에는 올리지 않고 생성된 JSON/README만 올리면 됩니다.

## 옵션 및 유지보수

- 상위 논문 수: `scholar-config.json`의 `top_n`을 수정(1–100).
- 기존 저장 데이터로 표만 재생성: `python3 scripts/update_scholar.py --from-cache`.
- 표의 시작/끝은 `<!-- SCHOLAR:START -->`, `<!-- SCHOLAR:END -->`. 한 쌍만 사용하세요.
- API 오류 대신 HTTP 차단/HTML 구조 변경/빈 결과를 감지합니다. 실패 시 이전 표를 빈 표로 덮어쓰지 않습니다.
- 처음부터 실제 데이터가 없으면 표를 임의로 만들지 않습니다.
- 연도가 없으면 `—`, 인용 수가 비어 있으면 0으로 표시합니다.
- 직접 HTTP 조회는 첫 페이지 최대 100개 기준이며 100개를 넘는 전체 논문 백업은 아닙니다.
- README에서 표 바깥의 기존 소개·링크·프로젝트 내용은 유지합니다.
- 푸시 권한 오류: Settings → Actions → General → Workflow permissions 및 보호 브랜치 정책을 확인하세요. 워크플로에는 `contents: write`를 지정했습니다.
- 외부 HTML이 바뀌면 추출기 수정이 필요할 수 있습니다.

## 테스트

```bash
python3 -m unittest discover -s tests -v
```

테스트는 만들어 놓은 HTML로 정렬, 인용 수 파싱, 특수문자, 프로필 검증, README 보존, 조회 실패 시 보존을 검사합니다.
테스트 통과는 Google에서 자동 조회를 허용한다는 의미가 아닙니다.

참고: https://scholar.google.com/intl/en/scholar/help.html
예약 실행: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
