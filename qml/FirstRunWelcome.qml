import QtQuick 2.15

Rectangle {
    id: root
    objectName: "firstRunWelcome"
    property var theme
    property var translator
    readonly property string activeLanguage: translator
        ? String(translator.language) : "en"
    signal beginRequested()

    color: theme.paper

    Column {
        anchors.centerIn: parent
        anchors.verticalCenterOffset: -Math.round(18 * root.theme.scale)
        width: Math.min(parent.width - root.theme.outerMargin * 2,
                        Math.round(520 * root.theme.scale))
        spacing: Math.round(34 * root.theme.scale)

        Text {
            width: parent.width
            text: "ktrmnl"
            color: root.theme.ink
            font.family: root.theme.displayFont
            font.pixelSize: Math.round(
                Math.min(root.width * 0.19, root.height * 0.23)
            )
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
        }

        ActionButton {
            objectName: "firstRunStartButton"
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(parent.width, Math.round(340 * root.theme.scale))
            height: root.theme.rowHeight
            theme: root.theme
            text: {
                var language = root.activeLanguage
                return root.translator.text("onboarding.begin_setup")
            }
            primary: true
            selected: true
            onRequested: root.beginRequested()
        }
    }
}
