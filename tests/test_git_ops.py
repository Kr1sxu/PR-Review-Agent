import subprocess, pytest

@pytest.fixture
def repo(tmp_path):
    d = tmp_path / "repo"; d.mkdir()
    subprocess.run(["git", "init"], cwd=str(d), capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(d), capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(d), capture_output=True)
    (d / "a.py").write_text("print('v1')\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(d), capture_output=True)
    subprocess.run(["git", "commit", "-m", "first"], cwd=str(d), capture_output=True)
    (d / "a.py").write_text("print('v2')\n", encoding="utf-8")
    (d / "b.py").write_text("# new\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(d), capture_output=True)
    subprocess.run(["git", "commit", "-m", "second"], cwd=str(d), capture_output=True)
    return d

class TestGitOps:
    def test_diff(self, repo):
        from src.tools.git_ops_tool import GitOps
        assert "v2" in GitOps(str(repo)).get_diff("HEAD~1", "HEAD")

    def test_file_content(self, repo):
        from src.tools.git_ops_tool import GitOps
        assert "v2" in GitOps(str(repo)).get_file_content("HEAD", "a.py")

    def test_changed_files(self, repo):
        from src.tools.git_ops_tool import GitOps
        files = GitOps(str(repo)).list_changed_files("HEAD~1", "HEAD")
        assert "a.py" in files and "b.py" in files

    def test_no_changes(self, repo):
        from src.tools.git_ops_tool import GitOps
        assert GitOps(str(repo)).list_changed_files("HEAD", "HEAD") == []

    def test_commit_message(self, repo):
        from src.tools.git_ops_tool import GitOps
        assert GitOps(str(repo)).get_commit_message("HEAD") == "second"

    def test_valid_ref(self, repo):
        from src.tools.git_ops_tool import GitOps
        ops = GitOps(str(repo))
        assert ops.is_valid_ref("HEAD") and not ops.is_valid_ref("bad_ref_abc")

    def test_invalid_repo(self, tmp_path):
        from src.tools.git_ops_tool import RepoNotFoundError
        from src.tools.git_ops_tool import GitOps, RepoNotFoundError
        with pytest.raises(RepoNotFoundError): GitOps(str(tmp_path))

    def test_invalid_commit(self, repo):
        from src.tools.git_ops_tool import CommitNotFoundError
        from src.tools.git_ops_tool import GitOps as GO, CommitNotFoundError as CNFE
        with pytest.raises(CNFE): GO(str(repo)).get_diff("bad_abc123", "HEAD")

