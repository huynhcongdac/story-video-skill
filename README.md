# Story Video: video truyện kể chuyện bằng AI, nhân vật giữ nguyên mặt

<p align="center"><img src="docs/preview.gif" width="240" alt="Trích đoạn video làm bằng skill này"></p>

Skill cho AI agent (Claude Code, Codex, Cursor…). Bạn đưa một ý tưởng, agent sẽ tự làm hết:
- viết kịch bản
- tạo nhân vật, bối cảnh, đạo cụ và khoảng 40 ảnh minh hoạ
- đọc lồng tiếng
- dựng thành **video dọc 3–5 phút** có đủ:
  - chuyển động Ken Burns
  - hiệu ứng giật kiểu CapCut
  - phụ đề hiện từng từ
  - thẻ nghi phạm, thẻ manh mối
  - đồng hồ đếm ngược "Bạn đoán ai là hung thủ?"

Hợp với: kênh truyện trinh thám, truyện bí ẩn, truyện đời, series có nhân vật lặp lại.

## Điểm khác biệt: nhân vật không bị đổi mặt
Mỗi nhân vật, bối cảnh và đạo cụ có một **bảng thiết kế nhiều góc**:
- **Nhân vật:** chân dung cận cảnh + dáng trước, nghiêng, sau.
- **Bối cảnh:** 4 góc máy.
- **Đạo cụ:** hình chiếu các mặt.

Mọi cảnh đều lấy các bảng này làm ảnh tham chiếu. Nhờ vậy, kể cả cảnh quay lưng hay cảnh đông người, nhân vật vẫn đúng mặt, đúng tóc, đúng trang phục. Làm series thì tập sau dùng lại đúng bảng thiết kế của tập trước.

## Chi phí
Mỗi tập cần khoảng **55–65 ảnh** (gồm 12–15 bảng thiết kế và 40–45 cảnh). Mỗi cảnh mang theo tới 6 ảnh tham chiếu.

| Nguồn ảnh | Giá tham khảo | Ghi chú |
|---|---|---|
| **sangtao.ai** (khuyên dùng) | Từ khoảng **200k / 500 ảnh** (khoảng 7 tập), xem [bảng giá](https://sangtao.ai/vi/imagine?tab=pricing) | Nhận tới 20 ảnh tham chiếu mỗi ảnh. Định dạng bảng thiết kế trong skill được chỉnh cho model này |
| OpenAI Images | Tính tiền theo từng ảnh | Ít ảnh tham chiếu hơn mỗi lần gọi |

Lưu ý: gọi qua API cần có gói hoặc credit, không có lượt miễn phí.
Đăng ký và lấy API key: https://sangtao.ai · Tài liệu API: https://sangtao.ai/vi/api-docs/chatgpt-image

Giọng đọc dùng **Vbee** hoặc **ElevenLabs**, bằng tài khoản của bạn. ElevenLabs có mốc thời gian từng từ nên phụ đề khớp tuyệt đối.

## Cài đặt
Cần có: Python 3.10+, Node.js 18+, ffmpeg.

```bash
# Claude Code: cài như một skill
git clone https://github.com/huynhcongdac/story-video-skill ~/.claude/skills/story-video
cd ~/.claude/skills/story-video
pip install numpy pillow
cp .env.example .env      # rồi điền SANGTAO_API_KEY và key giọng đọc
```

Sau đó chỉ cần nói với agent, ví dụ:
> Làm cho tôi một tập truyện trinh thám khoảng 4 phút, bối cảnh Sài Gòn những năm 90, thám tử là một bà cụ bán vé số.

Agent sẽ viết `story.json`, tạo ảnh, đọc giọng, dựng video, rồi gửi lại file `out/<tên-tập>.mp4`.

## Tự chạy từng bước (không cần agent)
```bash
cp -r examples/locked-room my-episode                     # ví dụ ngắn ~3 phút; hoặc tự viết story.json
python scripts/gen_assets.py my-episode sheets            # bảng thiết kế
python scripts/gen_assets.py my-episode keyframes         # ảnh cảnh
python scripts/tts.py my-episode                          # giọng đọc
python scripts/build_timeline.py my-episode               # timeline + âm thanh
python scripts/render.py my-episode --still 30 900        # xem thử vài khung
python scripts/render.py my-episode                       # → my-episode/out/my-episode.mp4
```
Ảnh nào chưa ưng thì sửa prompt trong `story.json` rồi tạo lại riêng ảnh đó:
`python scripts/gen_assets.py my-episode keyframes k_watch --force`

Cấu trúc `story.json`, danh sách hiệu ứng và mẹo viết kịch bản cho hấp dẫn: xem `SKILL.md`.

## Ghi chú
- **Dựng video bằng [Remotion](https://www.remotion.dev).** Remotion miễn phí cho cá nhân và công ty dưới 4 người; công ty lớn hơn cần mua giấy phép Remotion (xem trang giấy phép của Remotion).
- **Nhạc nền và hiệu ứng âm thanh được tổng hợp bằng code,** không dùng nhạc có bản quyền.
- **Chữ nhạy cảm trên phụ đề tự được che** (vd "chết" thành "ch\*t") để hạn chế bị nền tảng giảm tương tác. Giọng đọc giữ nguyên.
- **Chỉ dùng cho truyện hư cấu.** Không mô tả máu me; hãy tuân thủ quy định của nền tảng bạn đăng.

## Giấy phép
MIT (xem `LICENSE`). Remotion có giấy phép riêng.
