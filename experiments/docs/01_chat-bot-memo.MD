ユーザーシナリオ
- マネージャーは独自のリフレクション質問を作成できる
- メンバーはアンケートに回答することで、自分の取り組みを振り返ることができる
-----

オブジェクト
- Reflection（リフレクション）
 - リフレクションの質問・LLM/ユーザーメッセージ・回答などで構成される
- Reflection Items（リフレクション項目）
 - リフレクションの質問
- Report（レポート）
 - 必要な情報をすべて収集した後に生成される
-----

メモ
- ユーザーはGoogleフォームのような独自のアンケートを作成できる
- LLMはチャットを通じて、事前に設定されたすべてのデータを収集するために質問を続ける
- メンバーはテキストや音声メッセージで自由に回答できる。LLMが選択肢を提示することも可能（例：「1〜10のスケールで選んでください」）
---

ビュー（Notionページ）
- 基本的にすべてのデータはNotionに保存される
- 自動的に作成されるページは以下の通り
 - Reflection → マネージャーが確認可能
 - Reflection Items → マネージャーがアンケートを作成可能
 - Reflection Session
 - Reflection Message
 - Reflection Response
 - Reflection Report → マネージャーが各セッションの結果（質問と回答の組み合わせ）を確認可能
- 個人の成長サマリーをマネージャーが確認したい場合...
 - Individual Reports → マネージャーが作成し、関連付けを行う必要がある
-----

モデルオブジェクト（※実際のリレーションはNotionで構築。ここではRuby on Railsの記法を使用して説明）
Reflection
├── has_many :intake_items
├── has_many :intake_sessions
├── title: リフレクションのタイトル
└── description: このリフレクションの説明

ReflectionItem（質問の内容）
├── belongs_to :intake
├── name: 質問のタイトル
├── description: LLMへのプロンプト（ユーザーへの質問の仕方）
└── position: 質問の順番

ReflectionSession（Telegramチャットボットとの各リフレクションセッション）
├── belongs_to :reflection
├── belongs_to :member/unique user id（各SALASUSUメンバー）
├── has_many :reflection_messages
├── has_many :reflection_responses
├── has_one :reflection_report
└── status: open/close（ボットとのチャットで変更可能）
* 24時間以内に「open」のセッションがある場合、チャットボットがメンバーに「続けますか？終了しますか？」と確認する → statusプロパティに反映

ReflectionMessage（対話のログ）
├── belongs_to :reflection_session
├── role: assistant / user
└── content: メッセージの内容

ReflectionResponse（各質問に対する抽出済み回答）
├── belongs_to :reflection_session
├── belongs_to :reflection_item
└── content: リフレクションメッセージ（ユーザー・チャットボット間の対話）から抽出した回答

ReflectionReport（レポート）
├── belongs_to :reflection_session
└── generated_at: 作成日

Members（各SALASUSUメンバー）
├── user_id: 各SALASUSUメンバーの一意なユーザーID
├── telegram_id: Telegramから取得した一意なTelegram ID
├── telegram_user_name: 各SALASUSUメンバーがTelegramに設定した名前
└── generated_at: 作成日


リフレクション ダイアログフロー
1: メンバーが「*仮 reflection-bot」とのチャットを開き、テキストを送信する。Notionをチェックし、Openの会話がないかどうかを判断。＊常に英語・クメール語判定が動く
└── FastAPIへのWebhook（ウィンドウを開いたことを確認）※チャットを開いた瞬間にWebhookできない？ / 中途半端なSessionは自動削除？
   └── 「open」のセッションがある場合、チャットボットが「続けますか？終了しますか？」と確認
      ├── 「続ける」の場合: 既存のセッションを継続
       └── 「終了」の場合: セッションのstatusを「close」にし、「新しいセッションを開始しますか？」と確認
           └── 「YES」の場合: createSession(reflection:, member:, status: open) で新しいセッションを作成

2: LLM（チャットボット）が最初の項目を質問する
└── 質問が完了したら createMessage(role: assistant, content:...)

3: メンバーが回答する
└── 回答が完了したら createMessage(role: user, content:...)

4: LLMが回答を分析する
├── Tool Useを通じてReflectionResponseを抽出・保存
├── 次の質問がある場合は2に戻る
└── すべての質問が完了したら5へ進む

5: ReflectionReportを作成する
User Scenario
- Manager can create their own custom-reflection questions
- members can take the questionnaires and reflect their trials through answering the questionnaires.
-----

Objects
- Reflection
 - consists of questions of refection, LLM/user messages, response...etc
- Reflection Items
 - questions of reflection
- Report
 - will be generated after collecting all the info expected to be needed
-----

Memo
- User can create unique questionnaire like Google form
- LLM will keep asking questions through chat so that it can collect all the data which were pre-set
- members can answer with texts or voice messages freely. LLM can also show the options so that members can choose. (ex: "Select the scale from 1-10")
---

View (Notion Pages)
- Basically all the sata will be stored on Notion
- The pages that will be AUTOMATICALLY created are...
 - Reflection　-> Managers can see
 - Reflection Items -> Managers can create questionnaires
 - Reflection Session 
 - Reflection Message
 - Reflection Response
 - Reflection Report -> Managers can see the result of each session(combination of questions & answers)
-IF THE MANAGERS WANT TO SEE THE SUMMARY OF THE INDIVIDUAL GROWTH...
 - Individual reports -> Managers need to create and making the relation to 
-----

Model Objects (*Actual relation will be made with Notion. Here we use Ruby on Rails rules for easier understanding)
Reflection
├── has_many :intake_items
├── has_many :intake_sessions
├── title: Title of refection
└── description: explanation of this reflection

ReflectionItem (Contents of questions)
├── belongs_to :intake
├── name: question title
├── description: Prompt to LLM, how to ask questions to users
└── position: The order of the questions

ReflectionSession (Each reflection session with Telegram chat-bot)
├── belongs_to :reflection
├── belongs_to :member/unique user id (each SALASUSU members)
├── has_many :reflection_messages
├── has_many :reflection_responses
├── has_one :reflection_report
└── status: open/close (changeable with the chat with bot)
* IF there is "open" session within 24hrs, the chatbot asks members "you want to proceed or quit?" -> reflect ot status prop

ReflectionMessage (Logs of the dialogue)
├── belongs_to :reflection_session
├── role: assistant / user
└── content: contents of messages

ReflectionResponse (Extracted answer for each questions)
├── belongs_to :reflection_session
├── belongs_to :reflection_item
└── content: extracted answer from the reflection messages (dialog between user-chatbot)

ReflectionReport (Reporting)
├── belongs_to :reflection_session
└── generated_at: the date of the creation

Members (each SLASUSU members)
├── user_id: unique user id for each SALASUSU member
├── telegram_id: unique telegram id extracted from the telegram
├── telegram_user_name: name that each SALASUSU member set on the telegram
└── generated_at: the date of the creation


Reflection Dialog flow
1: Members start open the chat with "*temp reflection-bot", and send one text *MAKING SURE new session table will be created on telegram!!
└──Webhook to FastAPI for checking window-open.*開けた瞬間にWebhookできない？/*中途半端なSessionは自動削除？
   └──IF there is "open" session within 24hrs, the chatbot asks members "you want to proceed or quit?"
      ├──IF "proceed": continue the existing session
       └──IF "quit": status prop of the session will be "close", and chat asks user "Want to start new session?"
           └──IF "YES": create new session with createSession(reflection,: member:, status: open)

2: LLM(chat-bot) asks first item
└── When it is finish, createMessage(role: assistant, content:...)

3: Member will answer
└── When it is finish, createMessage(role: user, content:...)

4: LLM will analyse the answer
├──extract/save ReflectionResponse through Tool Use
├── if there is next question, goes back to 2
└── if all the questions finishes, goes to 5

5: Create ReflectionReport
├── createReflectionReport()
└── ReflectionSession.update(status: close)
-----

LLM Tool Use
- 対話中にLLMが使用するツール
 - reflection_response → ReflectionResponseに保存
 - complete_reflection → statusを「close」に変更し、ReflectionResponseを作成

-----
コードベース
- class Reflection/ReflectionSession...等
- function () ... → 作成が必要
-----
LLMオプション:
Haiku: メインのチャットボット機能用
Gemini: 文章生成・サマリー生成用

-----

システムプロンプト
あなたはリフレクションをサポートするアシスタントです。
LLm Tool use
- This is a tool LLM will use during the dialog
 - reflection_response -> save to ReflectionResponse
 - complete_reflection -> status change to "close", create ReflectionResponse

-----
Code base
- class Reflection/ReflectionSession...etc
- function () ...->need to be created
-----
LLM options:
Haiku: for the main chat-bot function
Gemini: sentence/summary generation

-----

System prompt
you are the assistant who support reflec
以下の項目について、相談者から情報を聞き出してください。

【Items】
{{#each reflection_items}}
- {{name}}: {{description}}
{{/each}}

- 1項目ずつ丁寧に聞いてください
- 十分な情報が得られたら record_response ツールで記録してください
- すべての項目が完了したら complete_intake を呼んでください
- 共感に基づき、優しく丁寧に聞いてください
-----

今後の拡張
Future extension
-----