from Constants.Cards import playerSets
import MainController
from conftest import sent_texts


class TestRoleAssignment:
    def test_correct_role_counts(self, bot, game_any):
        expected = playerSets[game_any.board.num_players]["roles"]
        actual = [game_any.playerlist[uid].role for uid in game_any.playerlist]
        for role in ("Liberal", "Fascist", "Hitler"):
            assert actual.count(role) == expected.count(role)

    def test_party_membership_matches_role(self, bot, game_any):
        for uid in game_any.playerlist:
            p = game_any.playerlist[uid]
            if p.role in ("Fascist", "Hitler"):
                assert p.party == "fascist"
            else:
                assert p.party == "liberal"


class TestFascistInformation:
    def test_5p_hitler_knows_fascist(self, bot, game5):
        bot.reset_mock()
        MainController.inform_fascists(bot, game5, 5)
        hitler = game5.get_hitler()
        fascists = game5.get_fascists()
        msgs = [c for c in bot.send_message.call_args_list if c[0][0] == hitler.uid]
        fellow_msgs = [c for c in msgs if "Your fellow fascist is" in str(c)]
        assert len(fellow_msgs) == 1
        assert fascists[0].name in str(fellow_msgs[0])

    def test_7p_hitler_does_not_know_fascists(self, bot, game7):
        bot.reset_mock()
        MainController.inform_fascists(bot, game7, 7)
        hitler = game7.get_hitler()
        msgs = [c for c in bot.send_message.call_args_list if c[0][0] == hitler.uid]
        assert not any("fellow fascist" in str(c) for c in msgs)

    def test_7p_fascists_know_hitler(self, bot, game7):
        bot.reset_mock()
        MainController.inform_fascists(bot, game7, 7)
        hitler = game7.get_hitler()
        for f in game7.get_fascists():
            msgs = [c for c in bot.send_message.call_args_list if c[0][0] == f.uid]
            hitler_msgs = [c for c in msgs if "Hitler is" in str(c)]
            assert len(hitler_msgs) == 1
            assert hitler.name in str(hitler_msgs[0])


class TestBoard:
    def test_initial_state(self, bot, game5):
        assert game5.board.state.liberal_track == 0
        assert game5.board.state.fascist_track == 0
        assert game5.board.state.failed_votes == 0

    def test_policy_deck(self, bot, game5):
        assert len(game5.board.policies) == 17
        assert game5.board.policies.count("liberal") == 6
        assert game5.board.policies.count("fascist") == 11

    def test_board_print(self, bot, game5):
        text = game5.board.print_board()
        for section in ("Liberal acts", "Fascist acts", "Election counter", "Presidential order"):
            assert section in text

    def test_5p_fascist_track(self, bot, game5):
        assert game5.board.fascist_track_actions == [None, None, "policy", "kill", "kill", "win"]

    def test_9p_fascist_track(self, bot, game9):
        assert game9.board.fascist_track_actions == ["inspect", "inspect", "choose", "kill", "kill", "win"]


class TestEnactPolicy:
    def _set_government(self, game):
        game.board.state.president = game.player_sequence[0]
        game.board.state.chancellor = game.player_sequence[1]

    def test_enact_liberal(self, bot, game5):
        self._set_government(game5)
        MainController.enact_policy(bot, game5, "liberal", False)
        assert game5.board.state.liberal_track == 1
        assert game5.board.state.failed_votes == 0

    def test_enact_fascist(self, bot, game5):
        self._set_government(game5)
        MainController.enact_policy(bot, game5, "fascist", False)
        assert game5.board.state.fascist_track == 1

    def test_liberal_win(self, bot, game5):
        self._set_government(game5)
        game5.board.state.liberal_track = 4
        MainController.enact_policy(bot, game5, "liberal", False)
        assert game5.board.state.game_endcode == 1
        assert any("liberals win" in m.lower() for m in sent_texts(bot))

    def test_fascist_win(self, bot, game5):
        self._set_government(game5)
        game5.board.state.fascist_track = 5
        MainController.enact_policy(bot, game5, "fascist", False)
        assert game5.board.state.game_endcode == -1
        assert any("fascists win" in m.lower() for m in sent_texts(bot))

    def test_anarchy_enacts_top_policy(self, bot, game5):
        top_policy = game5.board.policies[0]
        MainController.do_anarchy(bot, game5)
        if top_policy == "liberal":
            assert game5.board.state.liberal_track == 1
        else:
            assert game5.board.state.fascist_track == 1
        assert any("ANARCHY" in m for m in sent_texts(bot))


class TestVoting:
    def _vote_all(self, game, answer):
        for p in game.player_sequence:
            game.board.state.last_votes[p.uid] = answer

    def test_successful_vote(self, bot, game5):
        game5.board.state.nominated_president = game5.player_sequence[0]
        game5.board.state.nominated_chancellor = game5.player_sequence[1]
        self._vote_all(game5, "Ja")
        MainController.count_votes(bot, game5)
        assert game5.board.state.president == game5.player_sequence[0]
        assert game5.board.state.chancellor == game5.player_sequence[1]

    def test_failed_vote(self, bot, game5):
        game5.board.state.nominated_president = game5.player_sequence[0]
        game5.board.state.nominated_chancellor = game5.player_sequence[1]
        self._vote_all(game5, "Nein")
        MainController.count_votes(bot, game5)
        assert game5.board.state.failed_votes == 1
        assert any("didn't like" in m for m in sent_texts(bot))

    def test_three_failed_votes_triggers_anarchy(self, bot, game5):
        game5.board.state.failed_votes = 2
        game5.board.state.nominated_president = game5.player_sequence[0]
        game5.board.state.nominated_chancellor = game5.player_sequence[1]
        self._vote_all(game5, "Nein")
        MainController.count_votes(bot, game5)
        assert any("ANARCHY" in m for m in sent_texts(bot))


class TestHitlerElection:
    def test_hitler_as_chancellor_after_3_fascist(self, bot, game5):
        hitler = game5.get_hitler()
        non_hitler = [p for p in game5.player_sequence if p.role != "Hitler"][0]
        game5.board.state.fascist_track = 3
        game5.board.state.nominated_president = non_hitler
        game5.board.state.nominated_chancellor = hitler
        for p in game5.player_sequence:
            game5.board.state.last_votes[p.uid] = "Ja"
        MainController.count_votes(bot, game5)
        assert game5.board.state.game_endcode == -2
        assert any("fascists win" in m.lower() for m in sent_texts(bot))

    def test_non_hitler_chancellor_marked_safe(self, bot, game5):
        non_hitlers = [p for p in game5.player_sequence if p.role != "Hitler"]
        game5.board.state.fascist_track = 3
        game5.board.state.nominated_president = non_hitlers[0]
        game5.board.state.nominated_chancellor = non_hitlers[1]
        for p in game5.player_sequence:
            game5.board.state.last_votes[p.uid] = "Ja"
        MainController.count_votes(bot, game5)
        assert non_hitlers[1] in game5.board.state.not_hitlers
        assert game5.board.state.game_endcode == 0


class TestShufflePolicyPile:
    def test_shuffle_when_low(self, bot, game5):
        game5.board.discards = game5.board.policies[2:]
        game5.board.policies = game5.board.policies[:2]
        MainController.shuffle_policy_pile(bot, game5)
        assert len(game5.board.policies) == 17
        assert len(game5.board.discards) == 0

    def test_no_shuffle_when_enough(self, bot, game5):
        original_len = len(game5.board.policies)
        MainController.shuffle_policy_pile(bot, game5)
        assert len(game5.board.policies) == original_len
