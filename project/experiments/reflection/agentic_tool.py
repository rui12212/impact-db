# search_user: 
# 新規ユーザーかチェック。新規の場合は新しいカラムのセットをNotionで行い、returnで新規User IDを返す。
# 既存ユーザーの場合は既存UserIDを返す

# create_user
# 新規Userの作成

# check_open_session
# OpenのSessionがあるかを確認。ある場合は、Messageで「継続するかどうか」を確認。継続する場合は、ReflectItemを参照し、次の質問をreturn.
# それ以外の時は（closeのみ or データが何もない）、新規でSessionを作成

# create_session
# ReflectionSessionを新規作成->agentic_loopに託す

# create_message
# LLM/USerとの会話を一つ一つ保存

# create_response
# 質問に対する適切な回答があった場合に、Itemに対応するresponseを作成

# create_report
# 全てのResponseを埋められた場合に、Reportを作成

