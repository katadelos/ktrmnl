import QtQuick 2.15

Rectangle {
    id: root
    objectName: "trmnlIdPage"
    property var theme
    property var translator
    property string friendlyId: ""
    property string deviceName: ""
    readonly property string activeLanguage: translator
        ? String(translator.language) : "en"
    signal backRequested()

    color: theme.paper

    Column {
        anchors.centerIn: parent
        anchors.verticalCenterOffset: -Math.round(18 * root.theme.scale)
        width: parent.width - root.theme.outerMargin * 2
        spacing: Math.round(34 * root.theme.scale)

        Text {
            width: parent.width
            height: Math.round(root.height * 0.25)
            text: root.friendlyId
            textFormat: Text.PlainText
            color: root.theme.ink
            font.family: root.theme.displayFont
            font.pixelSize: Math.round(
                Math.min(root.width * 0.19, root.height * 0.23)
            )
            font.bold: true
            fontSizeMode: Text.Fit
            minimumPixelSize: root.theme.headingSize
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        Text {
            width: parent.width
            visible: root.deviceName.length > 0
            text: root.deviceName
            textFormat: Text.PlainText
            color: root.theme.ink
            font.family: root.theme.bodyFont
            font.pixelSize: root.theme.bodySize
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
        }

        ActionButton {
            objectName: "trmnlIdBackButton"
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(parent.width, Math.round(340 * root.theme.scale))
            height: root.theme.rowHeight
            theme: root.theme
            text: {
                var language = root.activeLanguage
                return root.translator.text("action.back")
            }
            primary: true
            selected: true
            onRequested: root.backRequested()
        }
    }
}
