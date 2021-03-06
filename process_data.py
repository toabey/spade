import sys
import codecs, re
import itertools
import operator
from nltk.corpus import wordnet as wn

class DataProcessor(object):
  def __init__(self, pred_arg_pos):
    # pred_arg_pos (list): List of strings that work as pos tags for predicate and arguments.
    # Examples: nsubj-dobj: ['v', 'n', 'n'], nn: ['n', 'n'], amod: ['n', 'a']
    self.pred_arg_pos = pred_arg_pos
    if len(pred_arg_pos) == 2:
        self.word_syn_cutoff = 3
        self.syn_path_cutoff = 5
        self.thing_syn_cutoff = 4
    else:
        # Recommendations for verb-subj-obj
        self.word_syn_cutoff = 2
        self.syn_path_cutoff = 5
        self.thing_syn_cutoff = 4

    self.thing_prons = ['it', 'which', 'that', 'this', 'what', 'these', 'itself', 'something', 'anything', 'everything'] # thing
    self.male_prons = ['he', 'him', 'himself', 'his'] # man.n.01
    self.female_prons = ['she', 'her', 'herself'] # woman.m.01
    self.people_prons = ['they', 'them', 'themselves', 'we', 'ourselves', 'yourselves'] # people.n.01, people.n.03
    self.person_prons = ['you', 'i', 'who', 'whom', 'whoever', 'anyone', 'everyone', 'myself', 'yourself'] # person.n.01
    
    self.thing_hypernyms = self.get_hypernyms_word('thing', 'n', syn_cutoff=self.thing_syn_cutoff)
    self.man_hypernyms = self.get_hypernyms_syn(wn.synset('man.n.01'))
    self.woman_hypernyms = self.get_hypernyms_syn(wn.synset('woman.n.01'))
    self.people_hypernyms = self.get_hypernyms_syn(wn.synset('people.n.01')).union(self.get_hypernyms_syn(wn.synset('people.n.03')))
    self.loc_hypernyms = self.get_hypernyms_syn(wn.synset('geographical_area.n.01'))
    self.person_hypernyms = self.get_hypernyms_syn(wn.synset('person.n.01'))
    self.year_hypernyms = self.get_hypernyms_syn(wn.synset('year.n.01'))
    self.number_hypernyms = self.get_hypernyms_syn(wn.synset('number.n.01'))

    self.misc_hypernyms = set(self.loc_hypernyms).union(self.person_hypernyms)

  def get_hypernyms_syn(self, syn, path_cutoff=-1):
    hypernyms = []
    for path_list in syn.hypernym_paths():
      pruned_path_list = list(path_list) if path_cutoff == -1 or path_cutoff >= len(path_list) else [x for x in reversed(path_list)][:path_cutoff]
      hypernyms.extend([s.name() for s in pruned_path_list])
    return set(hypernyms)

  def get_hypernyms_word(self, word, pos, syn_cutoff=-1):
    hypernyms = []
    synsets = wn.synsets(word, pos=pos)
    pruned_synsets = list(synsets) if syn_cutoff == -1 else synsets[:syn_cutoff]
    for syn in pruned_synsets:
      hypernyms.extend(list(self.get_hypernyms_syn(syn, path_cutoff=self.syn_path_cutoff)))
    return set(hypernyms)

  def make_data(self, filename, relaxed=False, handle_oov=True):
    datafile = codecs.open(filename, "r", "utf-8")
    x_data = []
    y_s_data = []
    word_hypernym_map = {}
    word_index = {}
    concept_index = {}
    word_freqs = {}
    concept_freqs = {}
    for line in datafile:
      line_parts = line.strip().split('\t')
      slot_hypernyms = []
      w_datum = []
      for i in range(0, len(line_parts)):
        word = line_parts[i]
        pos = self.pred_arg_pos[i]
        wrd_lower = word.lower()
        syns = wn.synsets(word, pos=pos)
        hypernyms = []
        if wrd_lower in self.thing_prons:
          hypernyms = list(self.thing_hypernyms)
        elif wrd_lower in self.male_prons:
          hypernyms = list(self.man_hypernyms)
        elif wrd_lower in self.female_prons:
          hypernyms = list(self.female_prons)
        elif wrd_lower in self.people_prons:
          hypernyms = list(self.people_hypernyms)
        elif wrd_lower in self.person_prons:
          hypernyms = list(self.person_hypernyms)
        elif len(syns) != 0:
          hypernyms = list(self.get_hypernyms_word(word, pos, syn_cutoff=self.word_syn_cutoff))
        elif re.match('^[12][0-9]{3}$', word) is not None:
          # The argument looks like an year
          hypernyms = list(self.year_hypernyms)
        elif re.match('^[0-9,-]+', word) is not None:
          hypernyms = list(self.number_hypernyms)
        elif word[0].isupper():
          hypernyms = list(self.misc_hypernyms)
        if len(hypernyms) == 0:
          hypernyms = [word]
        slot_hypernyms.append((word, hypernyms))
        if word not in word_index:
          word_index[word] = len(word_index)
        if word in word_freqs:
          word_freqs[word] += 1
        else:
          word_freqs[word] = 1  
        w_datum.append(word)

      for w, h_list in slot_hypernyms:
        for h in h_list:
          if h not in concept_index:
            concept_index[h] = len(concept_index)
        if h in concept_freqs:
          concept_freqs[h] += 1
        else:
          concept_freqs[h] = 1  
        if w not in word_hypernym_map:
          word_hypernym_map[w] = h_list
      
      w_hyp_inds = []
      for w in w_datum:
        w_hyps = word_hypernym_map[w]
        h_inds = [concept_index[y] for y in w_hyps]
        w_hyp_inds.append(h_inds)

      if relaxed:
        w_inds = [word_index[x] for x in w_datum]
        for i in range(len(w_datum)):
          x_data.append(w_inds + [i])
          y_s_data.append(w_hyp_inds[i])
      else:
        x_data.append([word_index[x] for x in w_datum])
        y_s_datum = [list(l) for l in itertools.product(*w_hyp_inds)]
        y_s_data.append(y_s_datum)
    if handle_oov:
      w_oov_num = int(0.01 * len(word_index))
      c_oov_num = int(0.01 * len(concept_index))
      w_oov = [w for w,_ in sorted(word_freqs.items(), key=operator.itemgetter(1))[:w_oov_num]]
      c_oov = [c for c,_ in sorted(concept_freqs.items(), key=operator.itemgetter(1))[:c_oov_num]]
      w_oov = set(w_oov)
      c_oov = set(c_oov)
      w_oov_ind = 0
      c_oov_ind = 0
      fixed_word_index = {'UNK': w_oov_ind}
      fixed_concept_index = {'UNK': c_oov_ind}
      w_ind_mapping = {}
      c_ind_mapping = {}
      for word in word_index:
        if word in w_oov:
          w_ind_mapping[word_index[word]] = w_oov_ind
        else:
          fixed_word_ind = len(fixed_word_index)
          fixed_word_index[word] = fixed_word_ind
          w_ind_mapping[word_index[word]] = fixed_word_ind
          
      for concept in concept_index:
        if concept in c_oov:
          c_ind_mapping[concept_index[concept]] = c_oov_ind
        else:
          fixed_concept_ind = len(fixed_concept_index)
          fixed_concept_index[concept] = fixed_concept_ind
          c_ind_mapping[concept_index[concept]] = fixed_concept_ind

      fixed_x_data = []
      fixed_y_s_data = []
      for x_datum, y_s_datum in zip(x_data, y_s_data):
        if relaxed:
          fixed_x_datum = [w_ind_mapping[ind] for ind in x_datum[:-1]]
          fixed_x_datum.append(x_datum[-1])
          fixed_y_s_datum = [c_ind_mapping[ind] for ind in y_s_datum]
        else:
          fixed_x_datum = [w_ind_mapping[ind] for ind in x_datum]
          fixed_y_s_datum = [[c_ind_mapping[ind] for ind in y_datum] for y_datum in y_s_datum]
        fixed_x_data.append(fixed_x_datum)
        fixed_y_s_data.append(fixed_y_s_datum)
      return fixed_x_data, fixed_y_s_data, fixed_word_index, fixed_concept_index, word_hypernym_map, w_oov, c_oov
    else:
      return x_data, y_s_data, word_index, concept_index, word_hypernym_map, set(), set()

