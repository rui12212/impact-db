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

Future extension
-----