def test_admin_page_uses_dashboard_layout(client):
    response = client.get("/admin")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert "问卷数据与兑奖后台" in response.text
    assert 'class="stats"' in response.text
    assert "每日答卷趋势" in response.text
    assert "异常原因分布" in response.text
    assert "每道题选项占比" in response.text
    assert "答卷明细与兑奖操作" in response.text
    assert "匿名参与标识" in response.text
    assert "删除测试答卷" in response.text
    assert "/purge" in response.text
    assert "questionStatsQuery" in response.text
    assert "status',status" in response.text
    assert "scope',scope" in response.text
    assert "days',days" in response.text
    assert "onchange=applyFilters" in response.text
    assert "refreshDashboardData" in response.text
    assert "dashboardRequestId" in response.text
