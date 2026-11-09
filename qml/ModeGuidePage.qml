import QtQuick 2.15

Rectangle {
    id: root
    objectName: "modeGuidePage"
    property var theme
    property var translator
    readonly property string activeLanguage: translator
        ? String(translator.language) : "en"
    signal finishRequested()

    color: theme.paper

    function translatedText(key) {
        var language = activeLanguage
        return translator.text(String(key))
    }

    PageHeader {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: root.theme.outerMargin
        anchors.rightMargin: root.theme.outerMargin
        theme: root.theme
        title: root.translatedText("onboarding.modes_title")
    }

    Column {
        id: modeList
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: header.bottom
        anchors.bottom: startButton.top
        anchors.leftMargin: root.theme.outerMargin
        anchors.rightMargin: root.theme.outerMargin
        anchors.topMargin: root.theme.compactMargin
        anchors.bottomMargin: root.theme.compactMargin

        Repeater {
            model: [
                {"title": "mode.trmnl", "description": "onboarding.mode_trmnl"},
                {"title": "mode.interrupt", "description": "onboarding.mode_interrupt"},
                {"title": "mode.local_short", "description": "onboarding.mode_local"},
                {"title": "mode.push_short", "description": "onboarding.mode_push"}
            ]

            delegate: Item {
                width: modeList.width
                height: Math.floor(modeList.height / 4)

                Text {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.round(parent.width * 0.25)
                    text: root.translatedText(modelData.title)
                    color: root.theme.ink
                    font.family: root.theme.displayFont
                    font.pixelSize: root.theme.bodySize
                    font.bold: true
                    elide: Text.ElideRight
                }

                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: Math.round(parent.width * 0.28)
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.translatedText(modelData.description)
                    color: root.theme.ink
                    font.family: root.theme.bodyFont
                    font.pixelSize: root.theme.detailSize
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: index < 3 ? root.theme.divider : 0
                    color: root.theme.ink
                }
            }
        }
    }

    ActionButton {
        id: startButton
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: root.theme.outerMargin
        anchors.rightMargin: root.theme.outerMargin
        anchors.bottomMargin: root.theme.compactMargin
        height: root.theme.rowHeight
        theme: root.theme
        text: root.translatedText("onboarding.start_ktrmnl")
        primary: true
        selected: true
        onRequested: root.finishRequested()
    }
}
