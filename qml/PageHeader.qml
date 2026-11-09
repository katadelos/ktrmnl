import QtQuick 2.15

Item {
    id: root
    property var theme
    property string title: ""
    property bool backVisible: false
    readonly property int backSlotWidth: Math.round(28 * theme.scale)
    readonly property int backTitleGap: Math.round(8 * theme.scale)
    signal backRequested()

    height: theme.headerHeight + theme.headerTopInset

    Text {
        anchors.left: parent.left
        anchors.leftMargin: root.backVisible ? root.backSlotWidth + root.backTitleGap : 0
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: root.theme.headerTopInset
        text: root.title
        color: root.theme.ink
        font.family: root.theme.displayFont
        font.pixelSize: root.theme.titleSize
        font.bold: true
        elide: Text.ElideRight
        verticalAlignment: Text.AlignVCenter
    }

    Rectangle {
        id: backButton
        objectName: "pageBackButton"
        visible: root.backVisible
        anchors.left: parent.left
        anchors.leftMargin: -root.theme.outerMargin
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: root.theme.headerTopInset
        anchors.bottomMargin: root.theme.divider
        width: root.backSlotWidth + root.theme.outerMargin
        color: backArea.highlighted ? root.theme.ink : root.theme.paper

        Image {
            id: backArrow
            objectName: "pageBackArrow"
            x: root.theme.outerMargin
            anchors.verticalCenter: parent.verticalCenter
            width: Math.round(11 * root.theme.scale)
            height: Math.round(21 * root.theme.scale)
            sourceSize: Qt.size(width, height)
            smooth: false
            readonly property color fillColor: backArea.highlighted
                ? root.theme.paper : root.theme.ink
            source: {
                var w = width
                var h = height
                var points = "0," + (h / 2 - 1) + " "
                    + w + ",0 " + w + "," + (w * 0.55) + " "
                    + (w * 0.45) + "," + (h / 2) + " "
                    + w + "," + (h - w * 0.55) + " " + w + "," + h + " "
                    + "0," + (h / 2 + 1)
                return "data:image/svg+xml," + encodeURIComponent(
                    '<svg xmlns="http://www.w3.org/2000/svg" width="' + w
                    + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h
                    + '"><polygon fill="' + fillColor + '" points="' + points
                    + '"/></svg>')
            }
        }

        PressArea {
            id: backArea
            anchors.fill: parent
            theme: root.theme
            onTriggered: root.backRequested()
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: root.theme.divider
        color: root.theme.ink
    }
}
