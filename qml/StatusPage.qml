import QtQuick 2.15

Rectangle {
    id: root
    objectName: "statusPage"
    property var theme
    property var translator
    property var rows: []
    readonly property string activeLanguage: translator
        ? String(translator.language) : "en"
    signal backRequested()

    function scroll(direction) {
        statusList.contentY = Math.max(0, Math.min(
            statusList.contentHeight - statusList.height,
            statusList.contentY + direction * root.theme.rowHeight))
    }

    color: theme.paper

    PageHeader {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: root.theme.outerMargin
        anchors.rightMargin: root.theme.outerMargin
        theme: root.theme
        backVisible: true
        onBackRequested: root.backRequested()
        title: {
            var language = root.activeLanguage
            return root.translator.text("status.title")
        }
    }

    Flickable {
        id: statusList
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        anchors.leftMargin: root.theme.outerMargin
        anchors.rightMargin: root.theme.outerMargin
        anchors.topMargin: root.theme.compactMargin
        anchors.bottomMargin: root.theme.compactMargin
        contentWidth: width
        contentHeight: statusRows.height
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: statusRows
            width: statusList.width
            Repeater {
                model: root.rows
                delegate: Item {
                    width: parent.width
                    height: Math.max(root.theme.rowHeight,
                                     Math.max(rowLabel.implicitHeight, rowValue.implicitHeight)
                                     + root.theme.compactMargin * 2)

                    Text {
                        id: rowLabel
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.round(parent.width * 0.33)
                        text: modelData.label
                        color: root.theme.ink
                        font.family: root.theme.displayFont
                        font.pixelSize: root.theme.detailSize
                        wrapMode: Text.Wrap
                    }

                    Text {
                        id: rowValue
                        anchors.left: parent.left
                        anchors.leftMargin: Math.round(parent.width * 0.36)
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.value
                        color: root.theme.ink
                        font.family: root.theme.bodyFont
                        font.pixelSize: root.theme.dialogBodySize
                        wrapMode: Text.Wrap
                        horizontalAlignment: Text.AlignLeft
                    }

                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: 1
                        color: root.theme.ink
                    }
                }
            }
        }
    }
}
